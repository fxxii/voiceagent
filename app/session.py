from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, AsyncIterator
from typing import Protocol

from fastapi import WebSocket

from app.audio import pcm16le_to_wav
from app.playback import stream_audio_message
from app.text import take_complete_sentences
from app.vad import TurnDetector, TurnEvent


class Transcriber(Protocol):
    async def transcribe(self, wav_audio: bytes, language: str | None = None) -> str: ...


class LanguageModel(Protocol):
    def stream_reply(
        self, messages: list[dict[str, str]]
    ) -> AsyncIterator[str]: ...


class Synthesizer(Protocol):
    async def synthesize(self, text: str) -> bytes: ...


SendAudio = Callable[[bytes], Awaitable[None]]


class VoicePipeline:
    def __init__(
        self,
        transcriber: Transcriber,
        language_model: LanguageModel,
        synthesizer: Synthesizer,
        *,
        language: str | None = None,
        system_prompt: str = "You are a concise telephone assistant.",
    ) -> None:
        self.transcriber = transcriber
        self.language_model = language_model
        self.synthesizer = synthesizer
        self.language = language
        self.system_prompt = system_prompt

    async def handle_turn(self, audio: bytes, send_audio: SendAudio) -> None:
        wav_audio = pcm16le_to_wav(audio)
        transcript = await self.transcriber.transcribe(wav_audio, self.language)
        if not transcript:
            return

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": transcript},
        ]
        pending = ""
        async for delta in self.language_model.stream_reply(messages):
            pending += delta
            sentences, pending = take_complete_sentences(pending)
            for sentence in sentences:
                await send_audio(await self.synthesizer.synthesize(sentence))

        if pending.strip():
            await send_audio(await self.synthesizer.synthesize(pending.strip()))


class CallLimiter:
    def __init__(self, max_calls: int = 1) -> None:
        if max_calls < 1:
            raise ValueError("max_calls must be positive")
        self.max_calls = max_calls
        self._active_calls = 0

    def try_acquire(self) -> bool:
        if self._active_calls >= self.max_calls:
            return False
        self._active_calls += 1
        return True

    def release(self) -> None:
        if self._active_calls:
            self._active_calls -= 1


class VoiceSession:
    def __init__(
        self,
        websocket: WebSocket,
        call_id: str,
        pipeline: VoicePipeline,
        *,
        detector: TurnDetector | None = None,
    ) -> None:
        self.websocket = websocket
        self.call_id = call_id
        self.pipeline = pipeline
        self.detector = detector or TurnDetector()
        self._turn_task: asyncio.Task[None] | None = None

    async def run(self) -> None:
        try:
            while True:
                message = await self.websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return
                if message.get("bytes") is not None:
                    await self._handle_audio(message["bytes"])
                elif message.get("text") is not None:
                    await self.websocket.send_json(
                        {"type": "ack", "call_id": self.call_id}
                    )
        finally:
            await self._cancel_turn()

    async def _handle_audio(self, chunk: bytes) -> None:
        for event in self.detector.feed(chunk):
            if event.kind == "speech_started":
                await self._cancel_turn()
            elif event.kind == "utterance" and event.audio:
                await self._start_turn(event.audio)

    async def _start_turn(self, audio: bytes) -> None:
        await self._cancel_turn()
        self._turn_task = asyncio.create_task(self._process_turn(audio))

    async def _process_turn(self, audio: bytes) -> None:
        try:
            await self.pipeline.handle_turn(audio, self._send_audio)
        except asyncio.CancelledError:
            raise
        except Exception:
            with contextlib.suppress(Exception):
                await self.websocket.send_json(
                    {
                        "type": "error",
                        "code": "provider_error",
                        "message": "voice provider unavailable",
                    }
                )

    async def _send_audio(self, mp3: bytes) -> None:
        await self.websocket.send_json(stream_audio_message(mp3))

    async def _cancel_turn(self) -> None:
        task = self._turn_task
        self._turn_task = None
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
