from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Document:
    doc_id: str
    pages: tuple[str, ...]


@dataclass(frozen=True)
class Citation:
    doc_id: str
    page: int  # 1-based
    quote: str


@dataclass(frozen=True)
class Claim:
    name: str
    value: str
    citation: Citation


@dataclass(frozen=True)
class Finding:
    sample_id: str
    attribute: str
    claims: tuple[Claim, ...]
    verdict: str  # "pass" or "exception"
