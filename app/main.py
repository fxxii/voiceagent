import os
from typing import Annotated

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field, field_validator

from app.providers import configured_edge_tts, configured_openrouter
from app.session import CallLimiter, VoicePipeline, VoiceSession
from app.ws_auth import HMACAuthenticator


app = FastAPI(title="Voice Gateway", version="0.1.0")
_documents: dict[str, "Document"] = {}
_ws_authenticator: HMACAuthenticator | None = None
_ws_authenticator_secret: str | None = None
_call_limiter: CallLimiter | None = None
_call_limiter_size: int | None = None


class Document(BaseModel):
    id: Annotated[str, Field(min_length=1)]
    text: Annotated[str, Field(min_length=1)]

    @field_validator("id", "text")
    @classmethod
    def reject_whitespace_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


def reset_state() -> None:
    """Clear process-local state for tests and local development."""

    global _call_limiter, _call_limiter_size
    _documents.clear()
    _call_limiter = None
    _call_limiter_size = None


def call_limiter() -> CallLimiter:
    global _call_limiter, _call_limiter_size

    configured_size = max(1, int(os.getenv("MEDIA_MAX_CONCURRENT_CALLS", "1")))
    if _call_limiter is None or configured_size != _call_limiter_size:
        _call_limiter = CallLimiter(configured_size)
        _call_limiter_size = configured_size
    return _call_limiter


def build_voice_pipeline() -> VoicePipeline | None:
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return None

    openrouter = configured_openrouter()
    return VoicePipeline(
        openrouter,
        openrouter,
        configured_edge_tts(),
        language=os.getenv("VOICE_LANGUAGE") or None,
        system_prompt=os.getenv(
            "VOICE_SYSTEM_PROMPT",
            "You are a concise telephone assistant.",
        ),
    )


def ws_authenticator() -> HMACAuthenticator | None:
    global _ws_authenticator, _ws_authenticator_secret

    secret = os.getenv("MEDIA_WS_HMAC_SECRET")
    if not secret:
        return None
    if secret != _ws_authenticator_secret:
        _ws_authenticator = HMACAuthenticator(secret)
        _ws_authenticator_secret = secret
    return _ws_authenticator


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, int | str]:
    return {"status": "ready", "documents": len(_documents)}


@app.websocket("/v1/audio/{call_id}")
async def audio_socket(websocket: WebSocket, call_id: str) -> None:
    authenticator = ws_authenticator()
    if authenticator is None:
        await websocket.accept()
        await websocket.close(code=1008, reason="media authentication is not configured")
        return

    try:
        authenticator.verify(call_id, websocket.headers)
    except ValueError:
        await websocket.accept()
        await websocket.close(code=1008, reason="media authentication failed")
        return

    await websocket.accept()
    limiter = call_limiter()
    if not limiter.try_acquire():
        await websocket.close(code=1013, reason="voice gateway is at capacity")
        return

    try:
        session = VoiceSession(
            websocket,
            call_id,
            build_voice_pipeline(),
        )
        await session.run()
    except WebSocketDisconnect:
        return
    finally:
        limiter.release()


@app.post("/v1/admin/documents", status_code=status.HTTP_201_CREATED)
def create_document(document: Document) -> dict[str, Document | int]:
    _documents[document.id] = document
    return {"document": document, "documents": len(_documents)}


@app.post("/v1/admin/reindex", status_code=status.HTTP_202_ACCEPTED)
def reindex() -> dict[str, int | str]:
    return {"status": "queued", "documents": len(_documents)}
