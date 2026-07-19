from __future__ import annotations

from dataclasses import dataclass


class CompatibilityError(RuntimeError):
    """The compatibility input or evidence failed closed."""


@dataclass(frozen=True, slots=True)
class Candidate:
    version: str
    gil: str
    release_date: str
    release_url: str
    source_url: str
    source_sha256: str
    linux_image: str


@dataclass(frozen=True, slots=True)
class CompatibilityMatrix:
    matrix_id: str
    uv_version: str
    requirements: tuple[str, ...]
    required_observations: tuple[str, ...]
    product_artifacts: tuple[str, ...]
    candidates: tuple[Candidate, ...]
    digest: str
