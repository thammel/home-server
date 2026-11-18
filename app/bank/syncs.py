"""Syncs waiting for a TAN or app approval, held in memory for a few minutes at most.

A parked session holds the PIN, so it is dropped (and the bank dialog closed) on timeout.
One sync per user at a time.
"""

import secrets
import threading
from dataclasses import dataclass

from app.bank.fints_backend import BankSession

SYNC_TIMEOUT_SECONDS = 5 * 60


@dataclass
class PendingSync:
    user_id: int
    session: BankSession
    since: object
    timer: threading.Timer


class SyncRegistry:
    def __init__(self, timeout: float = SYNC_TIMEOUT_SECONDS):
        self._timeout = timeout
        self._lock = threading.Lock()
        self._busy: set[int] = set()
        self._pending: dict[str, PendingSync] = {}

    def begin(self, user_id: int) -> bool:
        with self._lock:
            if user_id in self._busy:
                return False
            self._busy.add(user_id)
            return True

    def end(self, user_id: int):
        with self._lock:
            self._busy.discard(user_id)

    def is_busy(self, user_id: int) -> bool:
        with self._lock:
            return user_id in self._busy

    def park(self, user_id: int, session: BankSession, since) -> str:
        sync_id = secrets.token_urlsafe(16)
        timer = threading.Timer(self._timeout, self.expire, args=(sync_id,))
        timer.daemon = True
        with self._lock:
            self._pending[sync_id] = PendingSync(user_id, session, since, timer)
        timer.start()
        return sync_id

    def take(self, sync_id: str, user_id: int) -> PendingSync | None:
        """Hand a parked sync back to its owner; anyone else gets None."""
        with self._lock:
            pending = self._pending.get(sync_id)
            if pending is None or pending.user_id != user_id:
                return None
            del self._pending[sync_id]
        pending.timer.cancel()
        return pending

    def expire(self, sync_id: str):
        with self._lock:
            pending = self._pending.pop(sync_id, None)
        if pending is not None:
            pending.session.close()
            self.end(pending.user_id)

    def clear(self):
        for sync_id in list(self._pending):
            self.expire(sync_id)
        with self._lock:
            self._busy.clear()


registry = SyncRegistry()
