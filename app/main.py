from typing import Annotated

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field, field_validator


app = FastAPI(title="Voice Gateway", version="0.1.0")
_documents: dict[str, "Document"] = {}


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

    _documents.clear()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, int | str]:
    return {"status": "ready", "documents": len(_documents)}


@app.websocket("/v1/audio/{call_id}")
async def audio_socket(websocket: WebSocket, call_id: str) -> None:
    await websocket.accept()

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return

            if message.get("bytes") is not None:
                await websocket.send_bytes(message["bytes"])
            elif message.get("text") is not None:
                await websocket.send_json({"type": "ack", "call_id": call_id})
    except WebSocketDisconnect:
        return


@app.post("/v1/admin/documents", status_code=status.HTTP_201_CREATED)
def create_document(document: Document) -> dict[str, Document | int]:
    _documents[document.id] = document
    return {"document": document, "documents": len(_documents)}


@app.post("/v1/admin/reindex", status_code=status.HTTP_202_ACCEPTED)
def reindex() -> dict[str, int | str]:
    return {"status": "queued", "documents": len(_documents)}
