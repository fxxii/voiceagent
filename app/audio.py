from __future__ import annotations

import io
import wave


def pcm16le_to_wav(
    pcm: bytes,
    *,
    sample_rate: int = 8000,
    channels: int = 1,
) -> bytes:
    """Wrap PCM16LE bytes in a WAV container without changing the samples."""

    if not pcm:
        raise ValueError("PCM audio is required")
    if len(pcm) % 2:
        raise ValueError("PCM16 audio must contain complete samples")
    if sample_rate <= 0 or channels <= 0:
        raise ValueError("sample rate and channels must be positive")

    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return output.getvalue()
