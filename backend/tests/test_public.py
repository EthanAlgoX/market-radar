from app.connectors.public import parse_feed, query_matches


FEED = b'''<?xml version="1.0"?><rss version="2.0"><channel><title>Feed</title><item><guid>real-guid</guid><title>Central bank raises rates</title><link>https://example.org/press/1</link><description><![CDATA[<p>Policy update &amp; statement</p>]]></description><pubDate>Fri, 02 Oct 2026 04:00:00 GMT</pubDate></item><item><title>No date item</title><link>https://example.org/press/2</link></item><item><title>Unsafe link</title><link>javascript:alert(1)</link></item></channel></rss>'''


def test_rss_parser_keeps_original_links_dates_and_strips_html():
    posts = parse_feed(FEED, "rss", "Central Bank")
    assert len(posts) == 2
    assert posts[0]["url"] == "https://example.org/press/1"
    assert posts[0]["content"] == "Policy update & statement"
    assert posts[0]["published_at"] == "2026-10-02T04:00:00+00:00"
    assert posts[1]["published_at"] is None
    assert query_matches(posts[0], "Bitcoin OR Central bank")
    assert not query_matches(posts[0], "Bitcoin")
