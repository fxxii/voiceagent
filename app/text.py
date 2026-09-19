from __future__ import annotations

import re


_SENTENCE_PATTERN = re.compile(r".*?(?:[.!?]+(?=\s|$)|$)", re.DOTALL)
_COMPLETE_SENTENCE_PATTERN = re.compile(r".*?[.!?]+(?=\s|$)", re.DOTALL)


def split_sentences(text: str) -> list[str]:
    """Split response text into punctuation-complete chunks plus a final fragment."""

    sentences: list[str] = []
    remaining = text.strip()
    while remaining:
        match = _SENTENCE_PATTERN.match(remaining)
        if not match or not match.group(0):
            break
        sentence = match.group(0).strip()
        if sentence:
            sentences.append(sentence)
        remaining = remaining[match.end() :].strip()
        if sentence and sentence[-1] not in ".!?":
            break
    return sentences


def take_complete_sentences(text: str) -> tuple[list[str], str]:
    """Return complete sentence chunks and retain the unfinished suffix."""

    sentences: list[str] = []
    consumed = 0
    for match in _COMPLETE_SENTENCE_PATTERN.finditer(text):
        sentence = match.group(0).strip()
        if sentence:
            sentences.append(sentence)
        consumed = match.end()
    return sentences, text[consumed:].lstrip()
