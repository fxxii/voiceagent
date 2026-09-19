from __future__ import annotations

import base64


def stream_audio_message(mp3: bytes, *, sample_rate: int = 24000) -> dict[str, object]:
    if not mp3:
        raise ValueError("MP3 audio is required")
    return {
        "type": "streamAudio",
        "data": {
            "audioDataType": "mp3",
            "sampleRate": sample_rate,
            "audioData": base64.b64encode(mp3).decode("ascii"),
        },
    }
