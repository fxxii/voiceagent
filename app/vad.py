from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class VADConfig:
    sample_rate: int = 8000
    frame_ms: int = 20
    start_rms: float = 700.0
    end_rms: float = 400.0
    start_frames: int = 2
    silence_frames: int = 25
    min_speech_frames: int = 5
    max_utterance_ms: int = 8000

    @property
    def frame_bytes(self) -> int:
        return self.sample_rate * self.frame_ms // 1000 * 2

    @property
    def max_utterance_frames(self) -> int:
        return max(1, self.max_utterance_ms // self.frame_ms)


@dataclass(frozen=True)
class TurnEvent:
    kind: Literal["speech_started", "utterance"]
    audio: bytes | None = None


def _rms(frame: bytes) -> float:
    samples = struct.unpack(f"<{len(frame) // 2}h", frame)
    if not samples:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


class TurnDetector:
    """Dependency-free energy VAD for signed 16-bit little-endian PCM."""

    def __init__(self, config: VADConfig | None = None) -> None:
        self.config = config or VADConfig()
        if self.config.frame_bytes <= 0:
            raise ValueError("frame size must be positive")
        self._buffer = bytearray()
        self._pending: list[bytes] = []
        self._utterance: list[bytes] = []
        self._voiced_streak = 0
        self._speech_frames = 0
        self._silence_frames = 0

    def feed(self, chunk: bytes) -> list[TurnEvent]:
        if len(chunk) % 2:
            raise ValueError("PCM16 audio must contain complete samples")

        self._buffer.extend(chunk)
        events: list[TurnEvent] = []
        while len(self._buffer) >= self.config.frame_bytes:
            frame = bytes(self._buffer[: self.config.frame_bytes])
            del self._buffer[: self.config.frame_bytes]
            events.extend(self._feed_frame(frame))
        return events

    def _feed_frame(self, frame: bytes) -> list[TurnEvent]:
        level = _rms(frame)
        if not self._utterance:
            if level >= self.config.start_rms:
                self._pending.append(frame)
                self._voiced_streak += 1
                if self._voiced_streak >= self.config.start_frames:
                    self._utterance = list(self._pending)
                    self._pending.clear()
                    self._speech_frames = self._voiced_streak
                    self._silence_frames = 0
                    return [TurnEvent("speech_started")]
            else:
                self._pending.clear()
                self._voiced_streak = 0
            return []

        self._utterance.append(frame)
        if level >= self.config.end_rms:
            self._speech_frames += 1
            self._silence_frames = 0
        else:
            self._silence_frames += 1

        duration_reached = len(self._utterance) >= self.config.max_utterance_frames
        silence_reached = self._silence_frames >= self.config.silence_frames
        if (duration_reached or silence_reached) and self._speech_frames >= self.config.min_speech_frames:
            audio = b"".join(self._utterance)
            self._reset()
            return [TurnEvent("utterance", audio)]
        return []

    def _reset(self) -> None:
        self._pending.clear()
        self._utterance.clear()
        self._voiced_streak = 0
        self._speech_frames = 0
        self._silence_frames = 0
