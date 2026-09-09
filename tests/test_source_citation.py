"""Source citation / traceability tests (Section 6/26/35).

Every meaningful factual claim (news cluster, story analysis) must retain
a source_id/source_name/url trail back to where it came from.
"""
from __future__ import annotations

from src.analysis.story_analysis import analyze_stories
from src.models.schemas import NewsCluster
from src.processing.quality import run_quality_checks
from src.providers.mock_providers import MockLLMProvider


def make_cluster(cluster_id="c1", urls=None, source_ids=None, source_names=None):
    return NewsCluster(
        cluster_id=cluster_id,
        representative_article_id="a1",
        member_article_ids=["a1"],
        title="Some important market story",
        tickers=["NVDA"],
        themes=["ai_compute"],
        source_ids=source_ids if source_ids is not None else ["sec_edgar"],
        source_names=source_names if source_names is not None else ["SEC EDGAR"],
        source_tiers={"sec_edgar": 1},
        urls=urls if urls is not None else ["https://sec.gov/filing"],
        best_tier=1,
        fact_hint="A company disclosed something material.",
        hours_since_publish=5.0,
    )


def test_story_analysis_output_carries_source_ids():
    llm = MockLLMProvider()
    cluster = make_cluster()
    stories = analyze_stories(llm, [cluster], {})
    assert len(stories) == 1
    assert stories[0].source_ids == ["c1"]


def test_story_analysis_output_carries_urls():
    llm = MockLLMProvider()
    cluster = make_cluster(urls=["https://sec.gov/filing", "https://reuters.com/x"])
    stories = analyze_stories(llm, [cluster], {})
    assert set(stories[0].urls) == {"https://sec.gov/filing", "https://reuters.com/x"}


def test_quality_check_flags_missing_source_ids_on_story_analysis(settings):
    from src.models.schemas import ImportanceLevel, MarketSnapshot, StoryAnalysis
    from datetime import date, datetime, timezone as tz

    snapshot = MarketSnapshot(run_date=date(2026, 9, 9), generated_at=datetime.now(tz=tz.utc), assets=[MarketAssetStub() for _ in range(5)])
    story_missing_source = StoryAnalysis(
        cluster_id="c1", title="t", importance=ImportanceLevel.HIGH, fact="f", why_it_matters="w", source_ids=[],
    )
    status = run_quality_checks(snapshot, [make_cluster()], [story_missing_source], settings)
    assert any("source_ids" in r for r in status.reasons)


def test_quality_check_passes_when_sources_present(settings):
    from src.models.schemas import ImportanceLevel, MarketSnapshot, StoryAnalysis
    from datetime import date, datetime, timezone as tz

    snapshot = MarketSnapshot(run_date=date(2026, 9, 9), generated_at=datetime.now(tz=tz.utc), assets=[MarketAssetStub() for _ in range(5)])
    story_ok = StoryAnalysis(
        cluster_id="c1", title="t", importance=ImportanceLevel.HIGH, fact="f", why_it_matters="w", source_ids=["c1"],
    )
    status = run_quality_checks(snapshot, [make_cluster()], [story_ok], settings)
    assert status.degraded_mode is False


def MarketAssetStub():
    from src.models.schemas import MarketAsset

    return MarketAsset(symbol="X", display_name="X", group="g", daily_pct=0.1)
