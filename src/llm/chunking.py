# src/llm/chunking.py
"""Semantic chunking utilities.

The implementation is deliberately lightweight - it estimates token count by
splitting on whitespace (1 word ≈ 1 token) and splits the input text into
chunks that do not exceed ``max_tokens``.  A real implementation would use
sentence‑boundary detection and language‑model tokenizers, but for the purpose
of this project and the mocked tests a simple heuristic suffices.
"""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in *text*.

    This simple heuristic counts whitespace‑separated words.
    """
    return len(text.split())


def chunk_text(text: str, max_tokens: int) -> list[str]:
    """Split *text* into chunks not exceeding ``max_tokens``.

    The algorithm walks the text word‑by‑word, accumulating words until the
    token estimate would exceed ``max_tokens``; then it starts a new chunk.
    ``max_tokens`` must be a positive integer.
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens must be > 0")

    words = text.split()
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for w in words:
        if current_len + 1 > max_tokens:
            # Flush current chunk
            chunks.append(" ".join(current))
            current = []
            current_len = 0
        current.append(w)
        current_len += 1

    if current:
        chunks.append(" ".join(current))

    return chunks
