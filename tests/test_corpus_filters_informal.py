"""Active corpus must exclude informal Facebook sources (B2)."""

from groundtruth.analytics.corpus_filters import ACTIVE_CORPUS_WHERE, INFORMAL_SOURCE_WEBSITES


class TestInformalCorpusExclusion:
    def test_active_corpus_excludes_facebook(self) -> None:
        for source in INFORMAL_SOURCE_WEBSITES:
            assert f"'{source}'" in ACTIVE_CORPUS_WHERE
        assert "source_website NOT IN" in ACTIVE_CORPUS_WHERE
