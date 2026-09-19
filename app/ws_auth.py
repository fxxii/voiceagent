import hashlib
import hmac
import time
from collections.abc import Mapping


def signature_for(secret: str, call_id: str, timestamp: int, nonce: str) -> str:
    message = f"{call_id}\n{timestamp}\n{nonce}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


class HMACAuthenticator:
    def __init__(self, secret: str, max_skew_seconds: int = 30) -> None:
        if not secret:
            raise ValueError("HMAC secret is required")
        self.secret = secret
        self.max_skew_seconds = max_skew_seconds
        self._nonces: dict[str, int] = {}

    def verify(
        self,
        call_id: str,
        headers: Mapping[str, str],
        *,
        now: int | None = None,
    ) -> None:
        current_time = int(time.time()) if now is None else now

        def header(name: str) -> str | None:
            name = name.lower()
            for key, value in headers.items():
                if key.lower() == name:
                    return value
            return None

        header_call_id = header("x-call-id")
        if header_call_id != call_id:
            raise ValueError("call ID mismatch")

        raw_timestamp = header("x-timestamp")
        try:
            timestamp = int(raw_timestamp or "")
        except ValueError as exc:
            raise ValueError("invalid timestamp") from exc

        if abs(current_time - timestamp) > self.max_skew_seconds:
            raise ValueError("timestamp outside allowed window")

        nonce = header("x-nonce")
        if not nonce:
            raise ValueError("nonce is required")

        authorization = header("authorization") or ""
        prefix = "FS-HMAC "
        if not authorization.startswith(prefix):
            raise ValueError("invalid authorization")

        expected = signature_for(self.secret, call_id, timestamp, nonce)
        supplied = authorization[len(prefix) :]
        if not hmac.compare_digest(supplied, expected):
            raise ValueError("invalid signature")

        self._purge_expired(current_time)
        if nonce in self._nonces:
            raise ValueError("nonce replay detected")
        self._nonces[nonce] = timestamp + self.max_skew_seconds

    def _purge_expired(self, now: int) -> None:
        expired = [nonce for nonce, expires_at in self._nonces.items() if expires_at < now]
        for nonce in expired:
            del self._nonces[nonce]
