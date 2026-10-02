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
        {"id": "coindesk", "name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "enabled": True},
        {"id": "yahoo", "name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex", "enabled": True},
    ],
    "rsshub_url": "",
    "auto_refresh_minutes": 0,
    "llm": {"enabled": False, "base_url": "https://api.openai.com/v1", "model": "", "api_key": {"configured": False}},
}
