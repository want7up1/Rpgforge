from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable

VECTOR_DIMENSIONS = 1536
TOKEN_RE = re.compile(r"[a-z0-9_]{2,}", re.IGNORECASE)
CJK_RE = re.compile(r"[\u3400-\u9fff]+")


def extract_terms(text: str) -> list[str]:
    normalized = text.lower()
    terms: set[str] = set(TOKEN_RE.findall(normalized))

    for match in CJK_RE.finditer(text):
        run = match.group(0)
        if len(run) <= 4:
            terms.add(run)
        for size in (2, 3, 4):
            if len(run) < size:
                continue
            for index in range(0, len(run) - size + 1):
                terms.add(run[index : index + size])

    return sorted(term for term in terms if term.strip())


def text_to_vector(text: str, dimensions: int = VECTOR_DIMENSIONS) -> list[float] | None:
    terms = extract_terms(text)
    if not terms:
        return None

    values = [0.0] * dimensions
    for term in terms:
        digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        values[index] += sign * _term_weight(term)

    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 0:
        return None
    return [round(value / norm, 8) for value in values]


def cosine_similarity(vector_a: Iterable[float] | None, vector_b: Iterable[float] | None) -> float:
    if vector_a is None or vector_b is None:
        return 0.0

    list_a = list(vector_a)
    list_b = list(vector_b)
    if not list_a or not list_b or len(list_a) != len(list_b):
        return 0.0

    dot = sum(a * b for a, b in zip(list_a, list_b, strict=True))
    norm_a = math.sqrt(sum(a * a for a in list_a))
    norm_b = math.sqrt(sum(b * b for b in list_b))
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _term_weight(term: str) -> float:
    if len(term) <= 3:
        return 1.0
    return min(2.0, 1.0 + math.log10(len(term)))
