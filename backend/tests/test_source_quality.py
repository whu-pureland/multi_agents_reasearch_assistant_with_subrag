from __future__ import annotations

from app.research.source_quality import aggregate_quality, score_source


def test_quality_scoring_is_bounded() -> None:
    signals = score_source("https://example.com", title="hello", snippet="world")
    score = aggregate_quality(signals)
    assert 0.0 <= score <= 1.0


def test_gov_domain_scores_high() -> None:
    signals = score_source("https://www.cdc.gov/some/page", title="CDC guidance", snippet=None)
    score = aggregate_quality(signals)
    assert score >= 0.5

