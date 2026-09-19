from __future__ import annotations

import base64
import json
import os
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx


class ProviderError(RuntimeError):
    """An upstream speech or language provider returned an unusable result."""


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        *,
        stt_model: str = "openai/whisper-large-v3-turbo",
        llm_model: str = "openrouter/free",
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_seconds: float = 60.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenRouter API key is required")
        self.api_key = api_key
        self.stt_model = stt_model
        self.llm_model = llm_model
        self.base_url = base_url.rstrip("/")
        self._client = http_client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = http_client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def transcribe(self, wav_audio: bytes, language: str | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self.stt_model,
            "input_audio": {
                "data": base64.b64encode(wav_audio).decode("ascii"),
                "format": "wav",
            },
        }
        if language:
            payload["language"] = language

        try:
            response = await self._client.post(
                f"{self.base_url}/audio/transcriptions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderError("OpenRouter transcription failed") from exc

        text = result.get("text") if isinstance(result, dict) else None
        if not isinstance(text, str):
            raise ProviderError("OpenRouter transcription returned no text")
        return text.strip()

    async def stream_reply(
        self,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.llm_model,
            "messages": messages,
            "stream": True,
            "max_tokens": 256,
            "temperature": 0.2,
        }
        try:
            async with self._client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        event = json.loads(data)
                        delta = event["choices"][0].get("delta", {}).get("content", "")
                    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                        raise ProviderError("OpenRouter returned malformed stream data") from exc
                    if delta:
                        yield delta
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("OpenRouter language request failed") from exc


class EdgeTTSClient:
    def __init__(
        self,
        *,
        voice: str = "en-US-AriaNeural",
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
        communicate_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self.pitch = pitch
        self._communicate_factory = communicate_factory

    async def synthesize(self, text: str) -> bytes:
        if not text.strip():
            raise ValueError("TTS text is required")

        factory = self._communicate_factory
        if factory is None:
            try:
                import edge_tts
            except ImportError as exc:
                raise ProviderError("edge-tts is not installed") from exc
            factory = edge_tts.Communicate

        communicator = factory(
            text,
            voice=self.voice,
            rate=self.rate,
            volume=self.volume,
            pitch=self.pitch,
        )
        chunks: list[bytes] = []
        async for chunk in communicator.stream():
            if chunk.get("type") == "audio" and chunk.get("data"):
                chunks.append(chunk["data"])
        if not chunks:
            raise ProviderError("Edge TTS returned no audio")
        return b"".join(chunks)


def configured_openrouter() -> OpenRouterClient:
    return OpenRouterClient(
        os.getenv("OPENROUTER_API_KEY", ""),
        stt_model=os.getenv("OPENROUTER_STT_MODEL", "openai/whisper-large-v3-turbo"),
        llm_model=os.getenv("OPENROUTER_LLM_MODEL", "openrouter/free"),
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        timeout_seconds=float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "60")),
    )


def configured_edge_tts() -> EdgeTTSClient:
    return EdgeTTSClient(
        voice=os.getenv("EDGE_TTS_VOICE", "en-US-AriaNeural"),
        rate=os.getenv("EDGE_TTS_RATE", "+0%"),
        volume=os.getenv("EDGE_TTS_VOLUME", "+0%"),
        pitch=os.getenv("EDGE_TTS_PITCH", "+0Hz"),
    )
