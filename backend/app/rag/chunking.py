"""Recursive text chunking: paragraphs -> sentences -> hard character cut.

Size/overlap are in characters (cheap and model-agnostic; the embedding model
has a 256-wordpiece context and 1000 chars ~ 200-250 words, so chunks fit).
"""

from app.config import settings


def chunk_text(text: str, size: int | None = None, overlap: int | None = None) -> list[str]:
    size = size if size is not None else settings.chunk_size
    overlap = overlap if overlap is not None else settings.chunk_overlap
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError(f"invalid chunking config: size={size} overlap={overlap}")

    cleaned = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if not cleaned:
        return []
    if len(cleaned) <= size:
        return [cleaned]

    pieces = _split(cleaned, size)
    return _add_overlap(pieces, overlap)


def token_count(text: str) -> int:
    """Approximate token count (~4 chars/token, same heuristic as the router)."""
    return max(1, len(text) // 4) if text.strip() else 0


def _split(text: str, size: int) -> list[str]:
    """Split on paragraphs first, then sentences, then hard cuts, keeping
    every character exactly once and never exceeding `size` per piece."""
    if len(text) <= size:
        return [text]

    for separator in ("\n\n", "\n", ". "):
        parts = [p + separator for p in text.split(separator)]
        parts[-1] = parts[-1].removesuffix(separator)
        # Only useful when it actually breaks the text into viable pieces.
        if len(parts) > 1 and all(len(p) <= size for p in parts):
            return parts

    # No separator works: hard cut, but oversized "words" may still exist.
    return [text[i : i + size] for i in range(0, len(text), size)]


def _add_overlap(pieces: list[str], overlap: int) -> list[str]:
    if overlap == 0 or len(pieces) == 1:
        return [p.strip() for p in pieces if p.strip()]
    out: list[str] = []
    for i, piece in enumerate(pieces):
        chunk = piece.strip()
        if i > 0 and overlap:
            prev_tail = out[-1][-overlap:]
            # Start at a word boundary when one is nearby, to avoid mid-word glue.
            boundary = prev_tail.find(" ")
            if 0 < boundary < overlap // 2:
                prev_tail = prev_tail[boundary + 1 :]
            chunk = f"{prev_tail} {chunk}".strip()
        if chunk:
            out.append(chunk)
    return out
