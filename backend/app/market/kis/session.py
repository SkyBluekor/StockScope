from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from threading import Lock

from app.market.kis.models import KisEnvironment


@dataclass(slots=True)
class KisSession:
    app_key: str
    app_secret: str
    access_token: str
    environment: KisEnvironment
    expires_at: datetime

    @property
    def seconds_remaining(self) -> int:
        return max(0, int((self.expires_at - datetime.now(timezone.utc)).total_seconds()))


class InMemoryKisSessionStore:
    """Ephemeral KIS credential/token store.

    Credentials are never persisted to disk. This is deliberately in-memory only for
    the local PoC. A Cloudflare deployment will use an edge-safe ephemeral strategy.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, KisSession] = {}
        self._lock = Lock()

    def create(
        self,
        *,
        app_key: str,
        app_secret: str,
        access_token: str,
        environment: KisEnvironment,
        expires_in: int,
    ) -> tuple[str, KisSession]:
        now = datetime.now(timezone.utc)
        # Keep a small safety margin so we do not use a token at the exact expiry edge.
        ttl = max(60, expires_in - 30)
        session = KisSession(
            app_key=app_key,
            app_secret=app_secret,
            access_token=access_token,
            environment=environment,
            expires_at=now + timedelta(seconds=ttl),
        )
        session_id = token_urlsafe(32)
        with self._lock:
            self._purge_expired_unlocked(now)
            self._sessions[session_id] = session
        return session_id, session

    def get(self, session_id: str) -> KisSession | None:
        now = datetime.now(timezone.utc)
        with self._lock:
            self._purge_expired_unlocked(now)
            return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def _purge_expired_unlocked(self, now: datetime) -> None:
        expired = [key for key, value in self._sessions.items() if value.expires_at <= now]
        for key in expired:
            self._sessions.pop(key, None)


kis_sessions = InMemoryKisSessionStore()
