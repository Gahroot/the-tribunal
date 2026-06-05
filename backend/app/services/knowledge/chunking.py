"""Token-aware recursive-character text splitter.

Python port of noledge's ``src/lib/ingest/chunk.ts``: split a document into
overlapping, embedding-sized chunks while recording the exact ``char_start`` /
``char_end`` offsets of every chunk in the source text so callers can cite or
re-extract the original passage.

The splitter is *recursive* and *separator-aware* (paragraph → line → word →
character): it prefers to break on the coarsest separator that keeps a chunk
under the token budget, only falling back to finer separators for oversized
segments. It is *token-aware* (default ``cl100k_base`` via :mod:`tiktoken`,
which is the tokenizer ``text-embedding-3-small`` uses) so the ~400-token target
and 80-token overlap track real embedding cost rather than a char heuristic.

All offsets index the exact string handed to :func:`chunk_text`; ``content``
always equals ``text[char_start:char_end]`` (after whitespace trimming of the
chunk boundaries), so they round-trip losslessly.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()

# ── Defaults (mirror noledge chunk.ts) ──────────────────────────────────────
DEFAULT_TARGET_TOKENS = 400
DEFAULT_OVERLAP_TOKENS = 80
# Coarsest → finest. The empty string is the terminal "split between characters"
# separator used only for pathological, separator-free runs (e.g. a base64 blob).
DEFAULT_SEPARATORS: tuple[str, ...] = ("\n\n", "\n", " ", "")
# Rough chars-per-token used only for the char-window fallback + heuristic counter.
_APPROX_CHARS_PER_TOKEN = 4

# A token counter maps text → an integer token count.
TokenCounter = Callable[[str], int]


@dataclass(frozen=True, slots=True)
class TextChunk:
    """One embedding-sized slice of a document, with source-text offsets."""

    ordinal: int
    content: str
    char_start: int
    char_end: int
    token_count: int


# ── Token counting ──────────────────────────────────────────────────────────
_encoding_cache: object | None = None
_encoding_unavailable = False


def _tiktoken_count(text: str) -> int | None:
    """Token count via ``cl100k_base``; ``None`` if tiktoken is unavailable.

    The BPE table is loaded lazily and memoized. If loading fails (e.g. no
    network to fetch the encoding in a locked-down environment), we record the
    failure once and let the caller fall back to a char heuristic instead of
    paying the import/download cost on every call.
    """
    global _encoding_cache, _encoding_unavailable
    if _encoding_unavailable:
        return None
    if _encoding_cache is None:
        try:
            import tiktoken

            _encoding_cache = tiktoken.get_encoding("cl100k_base")
        except Exception as exc:  # noqa: BLE001 - degrade to heuristic, never crash ingest
            logger.warning("tiktoken_unavailable", error_type=type(exc).__name__)
            _encoding_unavailable = True
            return None
    return len(_encoding_cache.encode(text))  # type: ignore[attr-defined]


def default_token_counter(text: str) -> int:
    """Count tokens with ``cl100k_base``, falling back to a ~4-chars/token heuristic."""
    if not text:
        return 0
    counted = _tiktoken_count(text)
    if counted is not None:
        return counted
    return max(1, len(text) // _APPROX_CHARS_PER_TOKEN)


# ── Offset-preserving split helpers ─────────────────────────────────────────
def _segments_by_separator(text: str, start: int, end: int, sep: str) -> list[tuple[int, int]]:
    """Split ``text[start:end]`` on ``sep``, returning non-empty segment spans.

    The separator characters are dropped from the returned spans; because merging
    later spans a contiguous ``[first.start, last.end)`` range, the separators are
    transparently re-included in the merged chunk content.
    """
    segments: list[tuple[int, int]] = []
    pos = start
    sep_len = len(sep)
    while pos <= end:
        idx = text.find(sep, pos, end)
        if idx == -1:
            if pos < end:
                segments.append((pos, end))
            break
        if idx > pos:
            segments.append((pos, idx))
        pos = idx + sep_len
    return segments


def _char_windows(start: int, end: int, target: int) -> list[tuple[int, int]]:
    """Hard-split a separator-free run into ~``target``-token character windows."""
    window = max(1, target * _APPROX_CHARS_PER_TOKEN)
    spans: list[tuple[int, int]] = []
    pos = start
    while pos < end:
        stop = min(pos + window, end)
        spans.append((pos, stop))
        pos = stop
    return spans


def _split_spans(
    text: str,
    start: int,
    end: int,
    separators: Sequence[str],
    count_tokens: TokenCounter,
    target: int,
) -> list[tuple[int, int]]:
    """Recursively break ``text[start:end]`` into atomic spans ≤ ``target`` tokens."""
    if start >= end:
        return []
    substring = text[start:end]
    if not substring.strip():
        return []
    if count_tokens(substring) <= target or not separators:
        return [(start, end)]

    sep = separators[0]
    remaining = separators[1:]
    if sep == "":
        return _char_windows(start, end, target)

    segments = _segments_by_separator(text, start, end, sep)
    if not segments:
        # Separator absent in this range; try the next finer separator.
        return _split_spans(text, start, end, remaining, count_tokens, target)

    out: list[tuple[int, int]] = []
    for seg_start, seg_end in segments:
        if not text[seg_start:seg_end].strip():
            continue
        if count_tokens(text[seg_start:seg_end]) <= target:
            out.append((seg_start, seg_end))
        else:
            out.extend(_split_spans(text, seg_start, seg_end, remaining, count_tokens, target))
    return out


def _overlap_seed(
    text: str,
    spans: list[tuple[int, int]],
    cur: list[int],
    overlap: int,
    count_tokens: TokenCounter,
) -> list[int]:
    """Tail spans of ``cur`` whose cumulative tokens stay within ``overlap``."""
    if overlap <= 0:
        return []
    seed: list[int] = []
    total = 0
    for idx in reversed(cur):
        s, e = spans[idx]
        tok = count_tokens(text[s:e])
        if seed and total + tok > overlap:
            break
        seed.insert(0, idx)
        total += tok
        if total >= overlap:
            break
    # Never carry the whole chunk forward as overlap — that would stall progress.
    if len(seed) >= len(cur):
        return seed[1:]
    return seed


def _merge_spans(
    text: str,
    spans: list[tuple[int, int]],
    target: int,
    overlap: int,
    count_tokens: TokenCounter,
) -> list[tuple[int, int]]:
    """Greedily merge atomic spans into ≤ ``target``-token chunks with overlap."""
    if not spans:
        return []

    result: list[tuple[int, int]] = []
    cur: list[int] = []
    i = 0
    while i < len(spans):
        if not cur:
            cur = [i]
            i += 1
            continue
        cand_start = spans[cur[0]][0]
        cand_end = spans[i][1]
        if count_tokens(text[cand_start:cand_end]) <= target:
            cur.append(i)
            i += 1
            continue

        # Adding span ``i`` would overflow: emit the current chunk and reseed.
        result.append((spans[cur[0]][0], spans[cur[-1]][1]))
        seed = _overlap_seed(text, spans, cur, overlap, count_tokens)
        # Guarantee forward progress: if the overlap seed + span ``i`` still
        # overflows, start fresh so span ``i`` (always ≤ target) lands cleanly.
        if seed:
            seed_start = spans[seed[0]][0]
            if count_tokens(text[seed_start : spans[i][1]]) > target:
                seed = []
        cur = seed

    if cur:
        result.append((spans[cur[0]][0], spans[cur[-1]][1]))
    return result


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Shrink ``[start, end)`` past leading/trailing whitespace."""
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


# ── Public API ───────────────────────────────────────────────────────────────
def chunk_text(
    text: str,
    *,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    separators: Sequence[str] = DEFAULT_SEPARATORS,
    count_tokens: TokenCounter | None = None,
) -> list[TextChunk]:
    """Split ``text`` into overlapping, token-bounded chunks with char offsets.

    Args:
        text: Source document text. Offsets in the result index this exact string.
        target_tokens: Soft per-chunk token ceiling (~400 mirrors noledge).
        overlap_tokens: Tokens of trailing context carried into the next chunk.
        separators: Coarse→fine break points; the empty string is the terminal
            character-level split for separator-free runs.
        count_tokens: Token counter; defaults to ``cl100k_base`` (tiktoken).

    Returns:
        Ordinal-ordered chunks. ``content == text[char_start:char_end]`` for each.
        Empty / whitespace-only input yields an empty list.
    """
    if target_tokens <= 0:
        raise ValueError("target_tokens must be positive")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens must be non-negative")
    if overlap_tokens >= target_tokens:
        raise ValueError("overlap_tokens must be smaller than target_tokens")

    counter = count_tokens or default_token_counter
    if not text or not text.strip():
        return []

    spans = _split_spans(text, 0, len(text), separators, counter, target_tokens)
    merged = _merge_spans(text, spans, target_tokens, overlap_tokens, counter)

    chunks: list[TextChunk] = []
    ordinal = 0
    for raw_start, raw_end in merged:
        cs, ce = _trim_span(text, raw_start, raw_end)
        if cs >= ce:
            continue
        content = text[cs:ce]
        chunks.append(
            TextChunk(
                ordinal=ordinal,
                content=content,
                char_start=cs,
                char_end=ce,
                token_count=counter(content),
            )
        )
        ordinal += 1
    return chunks
