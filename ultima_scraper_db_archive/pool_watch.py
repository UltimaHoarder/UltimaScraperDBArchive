"""Opt-in report of database connections held too long (ULTIMA_DB_POOL_WATCH_SECONDS).

A retained pool with ``max_overflow=0`` fails every checkout once all of its
connections are held for longer than ``pool_timeout``. This watch records, at
checkout, the time, thread and first project caller of each connection (a
short frame walk, no stack capture). A daemon thread then reports any
connection held past the threshold, with the holder thread's current stack
and the pool status, and checkin reports the total hold time.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
import traceback
from typing import Any

from sqlalchemy import Engine, event
from ultima_scraper_core import runtime_env_value

_logger = logging.getLogger(__name__)
_SKIP = ("sqlalchemy", "sqlmodel", "pool_watch", "global_db.py", "contextlib", "threading.py", "concurrent")
_MAX_CALLER_FRAMES = 60
_STACK_FRAMES = 25


def watch_threshold_seconds() -> float:
    """The hold time worth reporting; 0 (the default) disables the watch."""
    raw = (runtime_env_value("ULTIMA_DB_POOL_WATCH_SECONDS") or "").strip()
    if not raw:
        return 0.0
    try:
        value = float(raw)
    except ValueError:
        _logger.warning("Ignoring invalid ULTIMA_DB_POOL_WATCH_SECONDS=%r", raw)
        return 0.0
    return value if value > 0 else 0.0


def _caller() -> str:
    """The first project frame above the pool, as ``path:line function``."""
    frame = sys._getframe(2)
    for _ in range(_MAX_CALLER_FRAMES):
        if frame is None:
            break
        name = frame.f_code.co_filename
        if "ultima_scraper" in name and not any(part in name for part in _SKIP):
            short = name.split("site-packages/")[-1].split("/USV/")[-1]
            return f"{short}:{frame.f_lineno} {frame.f_code.co_name}"
        frame = frame.f_back
    return "unknown"


def _stack(thread_ident: int) -> str:
    frame = sys._current_frames().get(thread_ident)
    if frame is None:
        return "  (thread has exited)"
    lines = traceback.format_stack(frame)[-_STACK_FRAMES:]
    return "".join(lines).rstrip()


class PoolWatch:
    def __init__(self, engine: Engine, threshold: float) -> None:
        self.engine = engine
        self.threshold = threshold
        self.held: dict[int, tuple[float, int, str]] = {}
        self.reported: set[int] = set()
        self.lock = threading.Lock()
        self.pid = os.getpid()
        self.thread: threading.Thread | None = None

    def checkout(self, _dbapi_connection: Any, record: Any, _proxy: Any) -> None:
        if self.thread is None or self.pid != os.getpid():
            self._start()
        with self.lock:
            self.held[id(record)] = (time.monotonic(), threading.get_ident(), _caller())

    def checkin(self, _dbapi_connection: Any, record: Any) -> None:
        with self.lock:
            entry = self.held.pop(id(record), None)
            reported = id(record) in self.reported
            self.reported.discard(id(record))
        if entry is None:
            return
        held = time.monotonic() - entry[0]
        if held >= self.threshold or reported:
            _logger.warning(
                "[PoolWatch] pid=%s connection returned after %.2fs (checked out by %s)",
                os.getpid(), held, entry[2],
            )

    def scan(self) -> int:
        """Report connections held past the threshold once each; returns the count."""
        now = time.monotonic()
        with self.lock:
            stale = [
                (key, entry) for key, entry in self.held.items()
                if now - entry[0] >= self.threshold and key not in self.reported
            ]
            self.reported.update(key for key, _ in stale)
            holding = len(self.held)
        for _key, (started, ident, caller) in stale:
            names = {thread.ident: thread.name for thread in threading.enumerate()}
            _logger.warning(
                "[PoolWatch] pid=%s connection held %.2fs by %s on thread %s; "
                "%d checked out, pool: %s\n%s",
                os.getpid(), now - started, caller, names.get(ident, ident), holding,
                self.engine.pool.status(), _stack(ident),
            )
        return len(stale)

    def _start(self) -> None:
        # After a fork the parent's records and thread do not exist here.
        with self.lock:
            if self.thread is not None and self.pid == os.getpid():
                return
            self.pid = os.getpid()
            self.held.clear()
            self.reported.clear()
            self.thread = threading.Thread(target=self._run, name="db-pool-watch", daemon=True)
            self.thread.start()

    def _run(self) -> None:
        interval = max(0.05, min(1.0, self.threshold / 2))
        while True:
            time.sleep(interval)
            try:
                self.scan()
            except Exception:  # noqa: BLE001 - diagnostics must never break the process
                _logger.debug("Pool watch scan failed", exc_info=True)


def install_pool_watch(engine: Engine, threshold: float | None = None) -> PoolWatch | None:
    """Attach the watch to ``engine`` when enabled; returns it, or None when off."""
    threshold = watch_threshold_seconds() if threshold is None else threshold
    if threshold <= 0:
        return None
    watch = PoolWatch(engine, threshold)
    event.listen(engine, "checkout", watch.checkout)
    event.listen(engine, "checkin", watch.checkin)
    _logger.info("[PoolWatch] pid=%s reporting connections held >= %.2fs", os.getpid(), threshold)
    return watch
