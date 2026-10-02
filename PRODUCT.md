# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The user researches trading information on their own computer and wants to read multiple public sources in one place.

## Product Purpose

A locally runnable website that collects information through keyword search and the user's connected X or Reddit account, then organizes it with source links. A separate watchlist collects public candles and explains price and volume events alongside relevant local news.

## Operating Context

The user's focus includes macroeconomics, cryptocurrency, US stocks, Hong Kong stocks, mainland China stocks, financial news, and gold. The reference projects are saved separately in ../reference.

## Capabilities and Constraints

English is the default interface language, with a persistent Chinese switch. Interface copy switches locally. Chinese source-content translation requires the user's own LLM API, configured in Settings → Translation or through a local environment fallback. Missing configuration must explain the requirement and link to the settings form. Preserve original posts and URLs, keep keys encrypted when entered in the UI, and never return credentials to the browser. Custom OpenAI-compatible providers and models are supported independently of optional AI summaries.

Keep keyword search, followed-author content, and account recommendations as independent ingestion channels. Followed content must not be discarded merely because it lacks a keyword. Preserve original URLs and source text. Personal access requires the user's own authorization; unconnected sources must display their actual status. Reddit's API homepage is not guaranteed to reproduce its website recommendation feed.

Market data has its own local database and manual refresh queue. The first implementation supports Binance USDT spot pairs at one hour, US/HK stocks and ETFs through Yahoo daily data, and mainland Shanghai/Shenzhen stocks through Eastmoney daily data. Preserve currency, volume units, timezone, source, adjustment, session and revisions. Confirm signals only from sufficient closed data; gaps, missing values and corporate actions must remain visible. The app does not execute trades or claim causal relationships between news and price changes.

## Evidence on Hand

Live public RSS and Hacker News, plus public Binance, Yahoo and Eastmoney candle samples. Personal X/Reddit paths are tested with offline responses; real account behavior still requires the user's authorization. No synthetic posts or fabricated market prices should appear as current data.

## Product Principles

- Start with reading and search, not a marketing page.
- Keep source provenance visible.
- Persist collected information before producing summaries.
- Make partial collection failures visible and recoverable.

## Open Decisions

Market Radar / 交易雷达 is a working name chosen for implementation. The user has not specified a brand or visual style. The first version assumes a single local user.
