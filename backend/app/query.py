"""Small deterministic finance aliases and provider-aware query compilation.

Aliases broaden only a complete known term. Unrecognised queries and provider
operators are preserved; local matching supports OR, AND, NOT and quoted phrases.
"""
from __future__ import annotations

import re

from .config import TOPIC_TERMS

ALIAS_GROUPS = (
    ("Federal Reserve", "美联储", "Fed", "FOMC"),
    ("central bank", "central banks", "央行"),
    ("inflation", "通胀", "通货膨胀"),
    ("interest rates", "interest rate", "利率"),
    ("rate cut", "rate cuts", "降息"),
    ("rate hike", "rate hikes", "加息"),
    ("gold", "gold price", "黄金", "金价", "XAUUSD"),
    ("silver", "silver price", "白银", "银价", "XAGUSD"),
    ("precious metals", "precious metal", "贵金属"),
    ("Bitcoin", "BTC", "$BTC", "比特币"),
    ("Ethereum", "ETH", "$ETH", "以太坊"),
    ("cryptocurrency", "cryptocurrencies", "crypto", "加密货币", "数字货币"),
    ("blockchain", "区块链"),
    ("US stocks", "US equities", "美股", "美国股市"),
    ("Nasdaq", "纳斯达克"),
    ("S&P 500", "标普500", "标普 500"),
    ("Hong Kong stocks", "港股"),
    ("Hang Seng", "恒生", "恒生指数"),
    ("China stocks", "A股", "A 股"),
    ("CSI 300", "沪深300", "沪深 300"),
    ("Nvidia", "NVDA", "$NVDA", "英伟达"),
    ("Tesla", "TSLA", "$TSLA", "特斯拉"),
    ("bank", "banks", "banking", "银行"),
    ("bond", "bonds", "债券"),
    ("financial markets", "金融市场"),
    ("GDP", "国内生产总值"),
    ("employment", "就业"),
    ("earnings", "财报", "业绩"),
)
_ALIAS_LOOKUP = {term.casefold(): group for group in ALIAS_GROUPS for term in group}
_OPERATORS = {"AND", "OR", "NOT"}
_PROVIDER_OPERATOR = re.compile(r"(?:^|\s)[\w]+:[^\s]+", re.UNICODE)


def _aliases(term: str) -> tuple[str, ...]:
    value = term.strip().strip('"')
    return _ALIAS_LOOKUP.get(value.casefold(), (value,))


def _tokens(query: str) -> list[str]:
    parts = re.split(r'("(?:[^"\\]|\\.)*"|[()]|\b(?:OR|AND|NOT)\b|[,，])', query, flags=re.I)
    tokens = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part in {",", "，"}:
            tokens.append("OR")
        elif part.upper() in _OPERATORS:
            tokens.append(part.upper())
        elif not part.startswith('"') and re.search(r"\s+-[^\s]+", part):
            first, *negative = re.split(r"\s+-(?=\S)", part)
            if first.strip():
                tokens.append(first.strip())
            for term in negative:
                tokens.extend(["AND", "NOT", term.strip()])
        else:
            tokens.append(part)
    return tokens


def _parse(query: str):
    tokens = _tokens(query)
    position = 0
    if len(tokens) > 256 or tokens.count("(") > 24:
        return ("TERM", query.strip())

    def atom():
        nonlocal position
        if position >= len(tokens):
            raise ValueError("missing query term")
        token = tokens[position]
        position += 1
        if token == "NOT":
            return ("NOT", atom())
        if token == "(":
            node = disjunction()
            if position >= len(tokens) or tokens[position] != ")":
                raise ValueError("unclosed query group")
            position += 1
            return node
        if token in _OPERATORS or token == ")":
            raise ValueError("invalid query operator")
        return ("TERM", token.strip('"'), token.startswith('"'))

    def conjunction():
        nonlocal position
        node = atom()
        while position < len(tokens) and tokens[position] not in {"OR", ")"}:
            if tokens[position] == "AND":
                position += 1
            node = ("AND", node, atom())
        return node

    def disjunction():
        nonlocal position
        node = conjunction()
        while position < len(tokens) and tokens[position] == "OR":
            position += 1
            node = ("OR", node, conjunction())
        return node

    if not tokens:
        return ("TERM", "")
    try:
        node = disjunction()
        if position != len(tokens):
            raise ValueError("unexpected query token")
        return node
    except ValueError:
        # Preserve arbitrary provider syntax rather than silently dropping user text.
        return ("TERM", query.strip())


def expand_query(query: str) -> list[str]:
    result: list[str] = []
    seen = set()

    def visit(node, negated=False):
        if node[0] == "TERM":
            if not negated:
                for term in _aliases(node[1]):
                    if term and term.casefold() not in seen:
                        seen.add(term.casefold())
                        result.append(term)
        elif node[0] == "NOT":
            visit(node[1], not negated)
        else:
            visit(node[1], negated)
            visit(node[2], negated)

    visit(_parse(query))
    return result[:32]


def compile_query(query: str, source: str) -> str:
    query = query.strip()
    if not query or _PROVIDER_OPERATOR.search(query):
        return query
    if source in {"hackernews", "hn"}:
        # Algolia's query parameter is text, not X/Google's boolean syntax.
        # The public connector issues separate positive searches then filters locally.
        group = _aliases(query)
        return next((term for term in group if term.isascii() and not term.startswith("$")), query)

    def quote(term):
        return '"' + term.replace('"', '\\"') + '"' if re.search(r"\s", term) else term

    implicit_and = source in {"x", "twitter", "news", "google", "google_news"}

    def compile_node(node, negated=False):
        kind = node[0]
        if kind == "NOT":
            return compile_node(node[1], not negated)
        if kind == "TERM":
            aliases = _aliases(node[1])
            if negated:
                if implicit_and:
                    return " ".join("-" + quote(term) for term in aliases)
                expression = "(" + " OR ".join(quote(term) for term in aliases) + ")" if len(aliases) > 1 else quote(node[1])
                return "NOT " + expression
            if len(aliases) == 1:
                return quote(node[1]) if len(node) > 2 and node[2] else node[1]
            return "(" + " OR ".join(quote(term) for term in aliases) + ")"
        # De Morgan preserves the meaning of exclusions of compound groups.
        operator = {"AND": "OR", "OR": "AND"}[kind] if negated else kind
        separator = " " if implicit_and and operator == "AND" else " " + operator + " "
        return "(" + compile_node(node[1], negated) + separator + compile_node(node[2], negated) + ")"

    return compile_node(_parse(query))


def _term_matches(text: str, term: str) -> bool:
    term = term.strip().strip('"')
    if not term:
        return True
    left = r"(?<![a-z0-9_])" if re.match(r"[a-z0-9_]", term, re.I) else ""
    right = r"(?![a-z0-9_])" if re.search(r"[a-z0-9_]$", term, re.I) else ""
    pattern = left + re.escape(term).replace(r"\ ", r"\s+") + right
    return re.search(pattern, text, re.I) is not None


def matches_query(text: str, query: str) -> bool:
    if not query.strip():
        return True

    def evaluate(node):
        kind = node[0]
        if kind == "TERM":
            return any(_term_matches(text, term) for term in _aliases(node[1]))
        if kind == "NOT":
            return not evaluate(node[1])
        if kind == "AND":
            return evaluate(node[1]) and evaluate(node[2])
        return evaluate(node[1]) or evaluate(node[2])

    return evaluate(_parse(query))


def classify_topics(text: str) -> list[str]:
    return [topic for topic, terms in TOPIC_TERMS.items() if any(matches_query(text, term) for term in terms)]
