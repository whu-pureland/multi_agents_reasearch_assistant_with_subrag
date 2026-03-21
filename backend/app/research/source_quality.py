from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class QualitySignal:
    score: float
    reason: str


_HIGH_TRUST_DOMAINS = {
    "nature.com",
    "science.org",
    "sciencedirect.com",
    "springer.com",
    "acm.org",
    "ieee.org",
    "who.int",
    "oecd.org",
    "worldbank.org",
}

_LOW_TRUST_HINTS = {"medium.com", "blogspot.", "wordpress.", "substack.com"}


def _domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    return host.lstrip("www.")


def score_source(url: str, title: str = "", snippet: str | None = None) -> list[QualitySignal]:
    signals: list[QualitySignal] = []
    domain = _domain(url)
    if not domain:
        return [QualitySignal(score=0.1, reason="missing_domain")]

    if domain.endswith(".gov") or domain.endswith(".edu"):
        signals.append(QualitySignal(score=0.9, reason="gov_or_edu"))

    if any(domain == d or domain.endswith("." + d) for d in _HIGH_TRUST_DOMAINS):
        signals.append(QualitySignal(score=0.8, reason="high_trust_domain"))

    if "wikipedia.org" in domain:
        signals.append(QualitySignal(score=0.5, reason="encyclopedia"))

    if any(hint in domain for hint in _LOW_TRUST_HINTS):
        signals.append(QualitySignal(score=-0.3, reason="low_trust_hint"))

    text = f"{title}\n{snippet or ''}".lower()
    if re.search(r"\bpdf\b", text):
        signals.append(QualitySignal(score=0.1, reason="pdf_hint"))
    if re.search(r"\bpeer[- ]review(ed)?\b", text):
        signals.append(QualitySignal(score=0.2, reason="peer_review_hint"))

    if not signals:
        signals.append(QualitySignal(score=0.3, reason="baseline"))
    return signals


def aggregate_quality(signals: list[QualitySignal]) -> float:
    score = 0.0
    for s in signals:
        score += s.score
    return max(0.0, min(1.0, score / max(1.0, len(signals))))

