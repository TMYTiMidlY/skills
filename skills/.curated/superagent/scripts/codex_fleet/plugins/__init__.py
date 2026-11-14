"""Source-only task plugins, reloaded at turn boundaries."""
from __future__ import annotations

import asyncio
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import inspect
import sys
import threading

_reload_lock = threading.RLock()


class FreshSource(importlib.machinery.SourceFileLoader):
    def get_code(self, fullname):
        # Compile source directly: timestamp-valid bytecode can be stale after
        # a same-second, same-length edit. Never delete a user's cache files.
        return compile(self.get_data(self.path), self.path, "exec")


class PluginFinder(importlib.abc.MetaPathFinder):
    def __init__(self, name: str, origin: str):
        self.name, self.origin = name, origin

    def find_spec(self, fullname, path=None, target=None):
        if fullname == self.name:
            return importlib.util.spec_from_loader(fullname, FreshSource(fullname, self.origin))
        return None


class Plugin:
    def __init__(self, module_name: str):
        self.name = module_name
        self.module = None

    def reload(self) -> None:
        with _reload_lock:
            importlib.invalidate_caches()
            spec = importlib.util.find_spec(self.name)
            if spec is None or not spec.origin or not spec.origin.endswith(".py"):
                raise TypeError("task plugins must be source Python modules")
            finder = PluginFinder(self.name, spec.origin)
            sys.meta_path.insert(0, finder)
            try:
                self.module = (importlib.reload(self.module) if self.module is not None
                               else importlib.import_module(self.name))
            finally:
                sys.meta_path.remove(finder)
        for name in ("prepare", "complete"):
            if not callable(getattr(self.module, name, None)):
                raise TypeError(f"plugin {self.name} missing {name}")

    async def call(self, name: str, *args):
        function = getattr(self.module, name)
        if inspect.iscoroutinefunction(function):
            return await function(*args)
        # Cancelling an await does not stop its thread or its external gate.
        # Keep the caller's lease and workspace locks until that thread finishes,
        # then propagate cancellation. Repeated cancellation keeps this fence.
        execution = asyncio.create_task(asyncio.to_thread(function, *args))
        cancelled = None
        while True:
            try:
                result = await asyncio.shield(execution)
                break
            except asyncio.CancelledError as exc:
                if execution.cancelled():
                    raise
                cancelled = exc
            except BaseException:
                if cancelled is not None:
                    raise cancelled
                raise
        if cancelled is not None:
            raise cancelled
        return await result if inspect.isawaitable(result) else result


__all__ = ["Plugin", "FreshSource"]
