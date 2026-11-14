"""Non-consuming SDK notification tap and per-turn observations.

The private router adaptation is confined to this module. An overflowing tap
fails explicitly; it never steals SDK subscriptions or reconstructs token flow.
"""
from __future__ import annotations

import asyncio
import collections
import re
import threading
from dataclasses import dataclass, field
from enum import StrEnum

RETRY = re.compile(r"reconnecting\s*(?:\.{3}|…)?\s*(\d+)\s*/\s*(\d+)", re.I)
TOOL_TYPES = {
    "commandExecution", "fileChange", "mcpToolCall", "dynamicToolCall",
    "collabAgentToolCall", "webSearch", "imageGeneration",
}


def unpack(notification) -> dict:
    payload = notification.payload
    if type(payload).__name__ == "UnknownNotification":
        data = payload.params
    else:
        data = payload.model_dump(mode="json", by_alias=True, exclude_none=True, warnings=False)
    return {"method": notification.method, "params": data or {}}


class Phase(StrEnum):
    IDLE = "IDLE"
    MODEL_STREAMING = "MODEL_STREAMING"
    TOOL_EXECUTING = "TOOL_EXECUTING"
    RECONNECTING = "RECONNECTING"


@dataclass
class TurnState:
    thread_id: str
    turn_id: str
    phase: Phase = Phase.IDLE
    attempt: int = 0
    max_attempts: int = 0
    overloaded: bool = False
    tools: set[str] = field(default_factory=set)

    def observe(self, event: dict) -> bool:
        method, params = event["method"], event["params"]
        turn = params.get("turnId") or (params.get("turn") or {}).get("id")
        if params.get("threadId") != self.thread_id or turn != self.turn_id:
            return False
        if method == "turn/completed":
            self.phase = Phase.IDLE
            self.tools.clear()
            return False
        if method == "error":
            message = str((params.get("error") or {}).get("message", ""))
            match = RETRY.search(message)
            if match or params.get("willRetry"):
                self.phase = Phase.RECONNECTING
                if match:
                    self.attempt, self.max_attempts = map(int, match.groups())
                fresh = not self.overloaded
                self.overloaded = True
                return fresh
            if any(word in message.lower() for word in ("at capacity", "overloaded", "too many requests")):
                fresh = not self.overloaded
                self.overloaded = True
                return fresh
        item = params.get("item") or {}
        if method == "item/started" and item.get("type") in TOOL_TYPES:
            self.tools.add(item["id"])
        elif method == "item/completed":
            self.tools.discard(item.get("id"))
        if method.startswith(("item/agentMessage/delta", "item/reasoning/")):
            self.phase = Phase.TOOL_EXECUTING if self.tools else Phase.MODEL_STREAMING
        elif self.phase != Phase.RECONNECTING and method in ("turn/started", "item/started", "item/completed"):
            self.phase = Phase.TOOL_EXECUTING if self.tools else Phase.MODEL_STREAMING
        return False


class DeferredGuidance:
    """Coalesce advice by key and apply it only to the next turn input."""

    def __init__(self):
        self.pending: dict[str, str] = {}

    def defer(self, key: str, text: str) -> None:
        self.pending[key] = text

    def append(self, text: str, subagents: int) -> str:
        tail = [f"本轮最多使用 {subagents} 个子代理；按任务需要协作，保持进行中的验证与授权边界。"]
        tail.extend(self.pending.values())
        self.pending.clear()
        return text + "\n\n[本轮调度建议]\n" + "\n".join(tail)


class SubagentTap:
    """Copy notifications before the instance router dispatches them."""

    def __init__(self, codex, max_events: int = 16384):
        if max_events < 1:
            raise ValueError("max_events must be positive")
        try:
            self.router = codex._client._sync._router
            self.original = self.router.route_notification
        except AttributeError as exc:
            raise RuntimeError("unsupported SDK router layout; validate this adapter before use") from exc
        self.loop = asyncio.get_running_loop()
        self.ready = asyncio.Event()
        self.lock = threading.Lock()
        self.buffer = collections.deque()
        self.max_events = max_events
        self.overflow = self.closed = False
        self.root: str | None = None
        self.children: set[str] = set()
        self.settled_children: set[str] = set()
        self.states: dict[tuple[str, str], TurnState] = {}

        def tee(notification):
            try:
                event = unpack(notification)
                with self.lock:
                    if not self.closed:
                        wake = not self.buffer
                        if len(self.buffer) < self.max_events:
                            self.buffer.append(event)
                        else:
                            wake = not self.overflow
                            self.overflow = True
                        if wake:
                            self.loop.call_soon_threadsafe(self.ready.set)
            finally:
                self.original(notification)

        self.tee = tee
        self.router.route_notification = tee

    async def next(self) -> dict:
        while True:
            with self.lock:
                if self.overflow:
                    raise RuntimeError("SubagentTap overflow: observation incomplete")
                if self.buffer:
                    event = self.buffer.popleft()
                    break
                if self.closed:
                    raise StopAsyncIteration
                self.ready.clear()
            await self.ready.wait()
        params = event["params"]
        item = params.get("item") or {}
        self.children.update(tid for tid in item.get("receiverThreadIds", []) if tid != self.root)
        tid = params.get("threadId") or (params.get("thread") or {}).get("id")
        if tid and self.root and tid != self.root:
            self.children.add(tid)
        turn = params.get("turnId") or (params.get("turn") or {}).get("id")
        if tid and turn:
            state = self.states.setdefault((tid, turn), TurnState(tid, turn))
            self.settled_children.discard(tid)
            event["overload"] = state.observe(event)
            event["phase"] = state.phase.value
        return event

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.next()

    def active_children(self) -> list[TurnState]:
        return [state for state in self.states.values()
                if state.thread_id in self.children and state.phase != Phase.IDLE]

    def unresolved_children(self) -> set[str]:
        observed = {state.thread_id for state in self.states.values()}
        return self.children - observed - self.settled_children

    def pending(self) -> bool:
        with self.lock:
            return bool(self.buffer)

    def close(self) -> None:
        with self.lock:
            self.closed = True
        if self.router.route_notification is self.tee:
            self.router.route_notification = self.original
        if not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self.ready.set)
