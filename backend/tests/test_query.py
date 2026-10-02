import pytest

from app.query import classify_topics, compile_query, expand_query, matches_query


def test_finance_aliases_are_bilingual_and_arbitrary_terms_survive():
    assert "Federal Reserve" in expand_query("美联储")
    assert "Bitcoin" in expand_query("比特币")
    assert expand_query("my unusual research phrase") == ["my unusual research phrase"]
    assert compile_query("my unusual research phrase", "news") == "my unusual research phrase"
    assert compile_query('"rare earth exports"', "news") == '"rare earth exports"'


@pytest.mark.parametrize("text", ["Goldman Sachs reports earnings", "golden retrievers", "bankruptcy cases", "FedEx earnings"])
def test_word_boundaries_avoid_finance_false_positives(text):
    assert not matches_query(text, "gold")
    if "bankruptcy" in text:
        assert not matches_query(text, "bank")
    if "FedEx" in text:
        assert not matches_query(text, "Fed")
    assert "gold" not in classify_topics(text)


def test_boolean_matching_and_negative_terms_use_bilingual_aliases():
    assert matches_query("Gold prices rise after a Federal Reserve rate cut", "黄金 AND 美联储 AND NOT 加息")
    assert not matches_query("Gold rises after a rate hike", "黄金 AND NOT 加息")
    assert matches_query("ETH rallies", "比特币 OR 以太坊")
    assert not matches_query("Bitcoin mining rises", "比特币 -mining")
    assert matches_query("Debt and banking", "银行,债券")
    assert matches_query("NVIDIA earnings", "英伟达")


@pytest.mark.parametrize("source", ["x", "news"])
def test_provider_boolean_compilation_uses_supported_exclusions(source):
    query = compile_query("黄金 AND NOT mining", source)
    assert "-mining" in query
    assert " NOT " not in query and " AND " not in query
    assert " OR " in query
    query = compile_query("黄金 AND NOT (mining OR inflation)", source)
    assert "-mining" in query and "-inflation" in query


def test_reddit_keeps_boolean_not_and_provider_operators_are_preserved():
    assert "NOT mining" in compile_query("黄金 AND NOT mining", "reddit")
    assert " AND " in compile_query("黄金 AND NOT mining", "reddit")
    assert compile_query("Bitcoin from:alice since:2026-01-01", "x") == "Bitcoin from:alice since:2026-01-01"
    assert compile_query("比特币", "hackernews") == "Bitcoin"
    assert expand_query("gold AND NOT mining") == list(expand_query("gold"))


def test_deep_or_malformed_queries_are_preserved_without_recursion_failure():
    query = "(" * 100 + "gold" + ")" * 100
    assert compile_query(query, "news") == query
    assert expand_query("gold AND") == ["gold AND"]
