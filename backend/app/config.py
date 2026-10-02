TOPICS = [
    {"id": "all", "name": "全部资讯", "query": "financial markets OR economy OR crypto"},
    {"id": "macro", "name": "宏观", "query": "Federal Reserve OR inflation OR 央行 OR 利率"},
    {"id": "crypto", "name": "加密货币", "query": "Bitcoin OR Ethereum OR cryptocurrency"},
    {"id": "us", "name": "美股", "query": "US stocks OR Nasdaq OR S&P 500"},
    {"id": "hk", "name": "港股", "query": "Hong Kong stocks OR Hang Seng OR 港股"},
    {"id": "cn", "name": "A股", "query": "China stocks OR CSI 300 OR A股"},
    {"id": "finance", "name": "金融", "query": "banking OR bonds OR financial markets"},
    {"id": "gold", "name": "黄金", "query": "gold price OR precious metals OR 黄金"},
]

TOPIC_TERMS = {
    "macro": ["federal reserve", "inflation", "央行", "利率", "central bank", "gdp", "economy", "employment"],
    "crypto": ["bitcoin", "ethereum", "cryptocurrency", "crypto", "btc", "区块链", "加密"],
    "us": ["nasdaq", "s&p", "wall street", "美股", "us stocks", "nvidia", "tesla"],
    "hk": ["hong kong", "hang seng", "港股", "恒生"],
    "cn": ["china stocks", "csi 300", "a股", "沪深", "上证", "深证"],
    "finance": ["bank", "bond", "financial", "finance", "银行", "金融", "债券"],
    "gold": ["gold", "precious metal", "黄金", "贵金属", "silver"],
}

DEFAULT_SETTINGS = {
    "keywords": ["Bitcoin", "Federal Reserve", "Nvidia", "gold"],
    "authors": {"x": [], "reddit": []},
    "reddit_subreddits": [],
    "rss_feeds": [
        {"id": "fed", "name": "Federal Reserve", "url": "https://www.federalreserve.gov/feeds/press_all.xml", "enabled": True},
        {"id": "ecb", "name": "European Central Bank", "url": "https://www.ecb.europa.eu/rss/press.html", "enabled": True},
        {"id": "coindesk", "name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss", "enabled": True},
        {"id": "yahoo", "name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex", "enabled": True},
        {"id": "cnbc-finance", "name": "CNBC Finance", "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html", "enabled": True},
        {"id": "hkex", "name": "HKEX News Releases", "url": "https://www.hkex.com.hk/Services/RSS-Feeds/News-Releases?sc_lang=en", "enabled": True},
    ],
    "rsshub_url": "",
    "google_news": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
    "auto_refresh_minutes": 0,
    "llm": {"enabled": False, "base_url": "https://api.openai.com/v1", "model": "", "api_key": {"configured": False}},
}


# Optional, source-specific choices. These do not silently alter existing users' subscriptions.
SOURCE_PRESETS = {
    "feeds": [
        {"id": "fed-monetary", "name": "Federal Reserve · Monetary Policy", "url": "https://www.federalreserve.gov/feeds/press_monetary.xml", "enabled": True, "category": "macro"},
        {"id": "fed", "name": "Federal Reserve · Press Releases", "url": "https://www.federalreserve.gov/feeds/press_all.xml", "enabled": True, "category": "macro"},
        {"id": "ecb", "name": "European Central Bank", "url": "https://www.ecb.europa.eu/rss/press.html", "enabled": True, "category": "macro"},
        {"id": "cnbc-finance", "name": "CNBC Finance", "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html", "enabled": True, "category": "us"},
        {"id": "hkex", "name": "HKEX News Releases", "url": "https://www.hkex.com.hk/Services/RSS-Feeds/News-Releases?sc_lang=en", "enabled": True, "category": "hk"},
        {"id": "coindesk", "name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss", "enabled": True, "category": "crypto"},
        {"id": "tradingview-aapl", "name": "TradingView · AAPL ideas", "url": "https://www.tradingview.com/feed/?symbol=NASDAQ%3AAAPL", "enabled": True, "category": "us"},
        {"id": "sec-10k", "name": "SEC · Latest 10-K filings", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&count=40&output=atom&owner=include&type=10-k", "enabled": False, "category": "us", "requires": ["declared_contact_user_agent", "access_validation"], "description": "官方 Atom；本次研究环境返回403，需单独验证访问。"},
    ],
    "rsshub_routes": [
        {"id": "wallstreetcn-global", "name": "华尔街见闻 · 全球快讯", "path": "/wallstreetcn/live/global", "category": "finance", "requires": []},
        {"id": "wallstreetcn-us", "name": "华尔街见闻 · 美股快讯", "path": "/wallstreetcn/live/us-stock", "category": "us", "requires": []},
        {"id": "wallstreetcn-hk", "name": "华尔街见闻 · 港股快讯", "path": "/wallstreetcn/live/hk-stock", "category": "hk", "requires": []},
        {"id": "wallstreetcn-commodity", "name": "华尔街见闻 · 商品快讯", "path": "/wallstreetcn/live/commodity", "category": "gold", "requires": []},
        {"id": "cls", "name": "财联社 · 电报", "path": "/cls/telegraph", "category": "cn", "requires": []},
        {"id": "gelonghui", "name": "格隆汇 · 快讯", "path": "/gelonghui/live", "category": "hk", "requires": []},
        {"id": "eastmoney-macro", "name": "东方财富 · 宏观研报", "path": "/eastmoney/report/macresearch", "category": "macro", "requires": []},
        {"id": "sse", "name": "上交所 · 公司公告", "path": "/sse/disclosure", "category": "cn", "requires": [], "description": "公告PDF原链接，非已抽取正文。"},
        {"id": "szse", "name": "深交所 · 公司公告", "path": "/szse/disclosure/listed/notice", "category": "cn", "requires": [], "description": "公告窗口有限，不保证完整历史。"},
        {"id": "pbc", "name": "人民银行 · 公开市场公告", "path": "/gov/pbc/tradeAnnouncement", "category": "macro", "requires": ["browser_runtime"]},
        {"id": "xueqiu-following", "name": "雪球 · 本人关注时间线", "path": "/xueqiu/timeline/-1", "category": "finance", "requires": ["XUEQIU_COOKIES", "isolated_personal_instance"]},
    ],
}
