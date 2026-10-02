# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The user researches trading information on their own computer and wants to read multiple public sources in one place.

## Product Purpose

A locally runnable website that collects information through keyword search and the user's connected X or Reddit account, then organizes it with source links.

## Operating Context

The user's focus includes macroeconomics, cryptocurrency, US stocks, Hong Kong stocks, mainland China stocks, financial news, and gold. The reference projects are saved separately in ../reference.

## Capabilities and Constraints

Keep keyword search, followed-author content, and account recommendations as independent ingestion channels. Followed content must not be discarded merely because it lacks a keyword. Preserve original URLs and source text. Personal access requires the user's own authorization; unconnected sources must display their actual status. Reddit's API homepage is not guaranteed to reproduce its website recommendation feed.

## Evidence on Hand

Live public RSS, Hacker News, and authorized social platform responses. No synthetic posts or fabricated market prices should appear as current data.

## Product Principles

- Start with reading and search, not a marketing page.
- Keep source provenance visible.
- Persist collected information before producing summaries.
- Make partial collection failures visible and recoverable.

## Open Decisions

Market Radar / 交易雷达 is a working name chosen for implementation. The user has not specified a brand or visual style. The first version assumes a single local user.
