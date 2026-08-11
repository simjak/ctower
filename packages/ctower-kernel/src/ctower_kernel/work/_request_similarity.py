"""Deterministic local hashed-subword embeddings for Request resemblance."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from itertools import pairwise

__all__ = ["ALGORITHM_REF", "MINIMUM_SIMILARITY", "LocalEmbedding", "embed", "similarity"]

ALGORITHM_REF = "ctower.local-hashed-subword/v1"
MINIMUM_SIMILARITY = 0.72
_DIMENSIONS = 2048
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class LocalEmbedding:
    """One fixed-dimension sparse embedding and its reproducibility digest."""

    values: tuple[tuple[int, float], ...]
    digest: bytes


def embed(text: str) -> LocalEmbedding:
    """Embed text without a model download, process call, secret, or network path."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    tokens = tuple(_TOKEN.findall(normalized))
    features: Counter[str] = Counter()
    features.update(f"word:{token}" for token in tokens)
    features.update(f"pair:{left}\0{right}" for left, right in pairwise(tokens))
    compact = " ".join(tokens)
    for width in (3, 4, 5):
        features.update(
            f"char{width}:{compact[index : index + width]}"
            for index in range(max(0, len(compact) - width + 1))
        )
    vector: Counter[int] = Counter()
    for feature, count in features.items():
        index = int.from_bytes(hashlib.sha256(feature.encode()).digest()[:4], "big") % _DIMENSIONS
        vector[index] += count
    values = tuple((index, float(value)) for index, value in sorted(vector.items()))
    canonical = ";".join(f"{index}:{value:.17g}" for index, value in values).encode()
    return LocalEmbedding(values, hashlib.sha256(canonical).digest())


def similarity(left: LocalEmbedding, right: LocalEmbedding) -> float:
    """Return deterministic cosine similarity rounded for stable persistence."""

    left_values = dict(left.values)
    right_values = dict(right.values)
    dot = sum(value * right_values.get(index, 0.0) for index, value in left_values.items())
    left_norm = math.sqrt(sum(value * value for value in left_values.values()))
    right_norm = math.sqrt(sum(value * value for value in right_values.values()))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return round(dot / (left_norm * right_norm), 6)
