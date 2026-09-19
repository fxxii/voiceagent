#!/usr/bin/env python3
"""Create the HMAC signature used by the FreeSWITCH media WebSocket."""

from __future__ import annotations

import argparse
import hashlib
import hmac
from pathlib import Path


def media_signature(secret: str, call_id: str, timestamp: int, nonce: str) -> str:
    message = f"{call_id}\n{timestamp}\n{nonce}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("call_id")
    parser.add_argument("timestamp", type=int)
    parser.add_argument("nonce")
    parser.add_argument(
        "--secret-file",
        type=Path,
        default=Path("/etc/freeswitch/edge-hmac.secret"),
    )
    args = parser.parse_args()

    secret = args.secret_file.read_text(encoding="utf-8").strip()
    if not secret:
        raise SystemExit("media HMAC secret is empty")
    print(media_signature(secret, args.call_id, args.timestamp, args.nonce))


if __name__ == "__main__":
    main()
