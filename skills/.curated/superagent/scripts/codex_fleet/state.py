"""Local SQLite control state, process-incarnation leases and kernel fences."""
from __future__ import annotations

import contextlib
import errno
import json
import os
import sqlite3
import sys
import threading
import time
import uuid
from pathlib import Path

if os.name == "posix":
    import fcntl
elif os.name == "nt":
    import msvcrt

# Level zero uses policy values; these are ceilings at degraded levels.
# The first drop reduces the default policy's subagent capacity immediately.
LADDER = [(3, 2), (3, 1), (2, 1), (2, 0), (1, 0)]


def identity(pid: int) -> str | None:
    """Linux boot ID plus process start ticks, excluding dead/zombie processes."""
    if type(pid) is not int or pid <= 0 or not sys.platform.startswith("linux"):
        return None
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        if fields[0] in ("Z", "X"):
            return None
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        return f"{boot_id}:{fields[19]}"
    except (OSError, IndexError):
        return None


class FileLock:
    """An owned byte/file lock; opening does not truncate existing lock files."""

    def __init__(self, path: Path, *, blocking: bool = False):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("a+b")
        try:
            if os.name == "posix":
                flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
                fcntl.flock(self.file, flags)
            elif os.name == "nt":
                self.file.seek(0, os.SEEK_END)
                if self.file.tell() == 0:
                    self.file.write(b"\0")
                    self.file.flush()
                self.file.seek(0)
                while True:
                    try:
                        msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError as exc:
                        if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                            raise
                        if not blocking:
                            raise BlockingIOError(exc.errno, "file lock is held", str(path)) from exc
                        time.sleep(0.05)
            else:
                raise RuntimeError(f"file locking is unavailable on {os.name}")
        except BaseException:
            self.file.close()
            raise

    def close(self) -> None:
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class State:
    """A single-host local WAL database. readonly=True never initializes it."""

    def __init__(self, path: Path, *, readonly: bool = False):
        self.path, self.readonly = Path(path), readonly
        if readonly:
            if not self.path.is_file():
                raise FileNotFoundError(self.path)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS workers(name TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS leases(worker TEXT PRIMARY KEY, token TEXT UNIQUE,
                    slot INTEGER UNIQUE, pid INTEGER, incarnation TEXT, expires REAL);
                CREATE TABLE IF NOT EXISTS overloads(thread_id TEXT, turn_id TEXT,
                    time REAL, detail TEXT, PRIMARY KEY(thread_id,turn_id));
                CREATE TABLE IF NOT EXISTS capacity(id INTEGER PRIMARY KEY CHECK(id=1),
                    level INTEGER, changed REAL, overloaded REAL);
                INSERT OR IGNORE INTO capacity VALUES(1,0,0,0);
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, time REAL,
                    worker TEXT, kind TEXT, data TEXT);
                CREATE TABLE IF NOT EXISTS imports(digest TEXT PRIMARY KEY, source TEXT, data TEXT);
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)

    @contextlib.contextmanager
    def connect(self, immediate: bool = False):
        if self.readonly and immediate:
            raise PermissionError("state database was opened read-only")
        db = None
        for attempt in range(6):
            try:
                location = self.path.resolve().as_uri() + "?mode=ro" if self.readonly else str(self.path)
                db = sqlite3.connect(location, uri=self.readonly, timeout=30)
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA busy_timeout=30000")
                if self.readonly:
                    db.execute("PRAGMA query_only=ON")
                else:
                    db.execute("PRAGMA synchronous=NORMAL")
                if immediate:
                    db.execute("BEGIN IMMEDIATE")
                break
            except sqlite3.OperationalError:
                if db is not None:
                    db.close()
                    db = None
                if attempt == 5:
                    raise
                time.sleep(0.05 * (attempt + 1))
        try:
            yield db
            if not self.readonly:
                db.commit()
        except BaseException:
            if not self.readonly:
                db.rollback()
            raise
        finally:
            db.close()

    def worker(self, name: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT data FROM workers WHERE name=?", (name,)).fetchone()
            return json.loads(row[0]) if row else {}

    def save(self, name: str, **changes) -> None:
        with self.connect(True) as db:
            row = db.execute("SELECT data FROM workers WHERE name=?", (name,)).fetchone()
            data = json.loads(row[0]) if row else {}
            data.update(changes, updated=time.time())
            db.execute("INSERT OR REPLACE INTO workers VALUES(?,?)", (name, json.dumps(data)))

    def event(self, name: str, kind: str, data: dict) -> None:
        if self.readonly:
            raise PermissionError("state database was opened read-only")
        with self.connect() as db:
            db.execute("INSERT INTO events(time,worker,kind,data) VALUES(?,?,?,?)",
                       (time.time(), name, kind, json.dumps(data, ensure_ascii=False)))

    def remember_account_order(self, order: list[str]) -> None:
        """Persist a forward account order; permit only unchanged-prefix extension."""
        if (not isinstance(order, list) or not order
                or any(not isinstance(name, str) or not name for name in order)
                or len(set(order)) != len(order)):
            raise ValueError("account order must contain distinct nonempty names")
        with self.connect(True) as db:
            row = db.execute("SELECT value FROM metadata WHERE key='account_order'").fetchone()
            previous = json.loads(row[0]) if row else []
            if order[:len(previous)] != previous:
                raise ValueError("account_order may only append to its persisted order")
            db.execute("INSERT OR REPLACE INTO metadata VALUES('account_order',?)", (json.dumps(order),))

    def overload(self, thread_id: str, turn_id: str, detail: str, retry_cap: int) -> bool:
        if not thread_id or not turn_id:
            raise ValueError("overload observations require thread and turn IDs")
        if type(retry_cap) is not int or not 0 <= retry_cap < len(LADDER):
            raise ValueError("invalid overload level cap")
        with self.connect(True) as db:
            now = time.time()
            added = db.execute("INSERT OR IGNORE INTO overloads VALUES(?,?,?,?)",
                               (thread_id, turn_id, now, detail)).rowcount
            if added:
                db.execute("UPDATE capacity SET level=min(level+1,max(level,?)),changed=?,overloaded=? WHERE id=1",
                           (retry_cap, now, now))
            else:
                # Persistent dedup prevents repeated drops, not health refreshes.
                db.execute("UPDATE capacity SET overloaded=? WHERE id=1", (now,))
            return bool(added)

    def _limits(self, db, policy: dict) -> tuple[int, int, int]:
        row = db.execute("SELECT * FROM capacity WHERE id=1").fetchone()
        level = row["level"]
        if type(level) is not int or not 0 <= level < len(LADDER):
            raise ValueError("invalid persisted capacity level")
        if level and time.time() - max(row["changed"], row["overloaded"]) >= policy["recovery_seconds"]:
            level -= 1
            db.execute("UPDATE capacity SET level=?,changed=? WHERE id=1", (level, time.time()))
        workers, subagents = (LADDER[level] if level else
                              (policy["max_parallel_workers"], policy["max_subagents_per_worker"]))
        return min(workers, policy["max_parallel_workers"]), min(subagents, policy["max_subagents_per_worker"]), level

    def limits(self, policy: dict) -> tuple[int, int, int]:
        with self.connect(True) as db:
            return self._limits(db, policy)

    def acquire(self, name: str, policy: dict):
        incarnation = identity(os.getpid())
        if incarnation is None:
            raise RuntimeError("fleet leases require Linux /proc process-incarnation support")
        held = None
        with self.connect(True) as db:
            now = time.time()
            for row in db.execute("SELECT * FROM leases").fetchall():
                observed = identity(row["pid"])
                if row["expires"] <= now or observed is None or observed != row["incarnation"]:
                    db.execute("DELETE FROM leases WHERE token=?", (row["token"],))
            flags = policy["workers"].get(name, {})
            if flags.get("pause") or flags.get("drain"):
                return None
            max_workers, _, _ = self._limits(db, policy)
            rows = db.execute("SELECT worker,slot FROM leases").fetchall()
            if len(rows) >= max_workers or any(row["worker"] == name for row in rows):
                return None
            used = {row["slot"] for row in rows}
            for slot in range(max_workers):
                if slot in used:
                    continue
                try:
                    held = FileLock(self.path.parent / "slots" / f"{slot}.lock")
                    try:
                        with FileLock(self.path.parent / "slots" / f"{slot}.runtime.lock"):
                            pass
                    except BlockingIOError:
                        held.close()
                        held = None
                        continue
                    break
                except BlockingIOError:
                    continue
            if held is None:
                return None
            token, expires = uuid.uuid4().hex, now + policy["lease_seconds"]
            try:
                db.execute("INSERT INTO leases VALUES(?,?,?,?,?,?)",
                           (name, token, slot, os.getpid(), incarnation, expires))
            except BaseException:
                held.close()
                raise
        return Lease(self, token, held, policy["lease_seconds"], slot, expires)

    def snapshot(self) -> dict:
        with self.connect() as db:
            workers = {row["name"]: json.loads(row["data"]) for row in db.execute("SELECT * FROM workers")}
            for checkpoint in workers.values():
                expected = checkpoint.get("process_identity")
                checkpoint["process_alive"] = bool(expected) and identity(checkpoint.get("pid", 0)) == expected
            return {
                "workers": workers,
                "leases": [dict(row, alive=bool(row["incarnation"]) and identity(row["pid"]) == row["incarnation"],
                                expired=row["expires"] <= time.time())
                           for row in db.execute("SELECT * FROM leases")],
                "capacity": dict(db.execute("SELECT * FROM capacity WHERE id=1").fetchone()),
                "overload_count": db.execute("SELECT count(*) FROM overloads").fetchone()[0],
            }


class Lease:
    """A token-bound heartbeat independent from the worker's asyncio loop."""

    def __init__(self, state, token, held, ttl, slot, expires=None):
        self.state, self.token, self.held, self.ttl = state, token, held, ttl
        self.expires = time.time() + ttl if expires is None else expires
        self.stop, self.lost = threading.Event(), threading.Event()
        self.thread: threading.Thread | None = None
        self.runtime_fence = str(state.path.parent / "slots" / f"{slot}.runtime.lock")
        self.closed = False

    def renew(self) -> bool:
        with self.state.connect(True) as db:
            now, new_expires = time.time(), time.time() + self.ttl
            changed = db.execute("UPDATE leases SET expires=? WHERE token=? AND expires>?",
                                 (new_expires, self.token, now)).rowcount
            if changed:
                self.expires = new_expires
            else:
                self.lost.set()
            return bool(changed)

    def start(self):
        if self.thread is not None:
            raise RuntimeError("lease heartbeat has already started")

        def heartbeat():
            interval = min(5.0, self.ttl / 4)
            while not self.stop.wait(interval):
                try:
                    if not self.renew():
                        return
                    interval = min(5.0, self.ttl / 4)
                except Exception:
                    if time.time() >= self.expires:
                        self.lost.set()
                        return
                    interval = min(1.0, max(0.05, (self.expires - time.time()) / 4))

        self.thread = threading.Thread(target=heartbeat, daemon=True, name="fleet-lease-heartbeat")
        self.thread.start()
        return self

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=16)
        try:
            with self.state.connect(True) as db:
                db.execute("DELETE FROM leases WHERE token=?", (self.token,))
        finally:
            self.held.close()
