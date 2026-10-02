from __future__ import annotations

import hashlib
import json
import sqlite3
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .config import DEFAULT_SETTINGS, TOPICS
from .translation import source_hash


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class ItemVersionConflict(ValueError):
    """A delayed enrichment must not overwrite a newer source revision."""


def canonical_url(url: str) -> str:
    """Normalize tracking only; preserve meaningful paths, query values and scheme."""
    parsed = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
             if not key.casefold().startswith("utm_") and key.casefold() not in {"fbclid", "gclid", "mc_cid", "mc_eid"}]
    fragment = parsed.fragment if parsed.fragment.startswith(("/", "!")) else ""
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, urlencode(sorted(query, key=lambda pair: pair[0])), fragment))


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.translation_model = None
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS items (
                    id TEXT PRIMARY KEY, source TEXT NOT NULL, external_id TEXT NOT NULL,
                    url TEXT NOT NULL, published_at TEXT, collected_at TEXT NOT NULL,
                    value TEXT NOT NULL, bookmarked INTEGER NOT NULL DEFAULT 0,
                    is_read INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(source, external_id)
                );
                CREATE INDEX IF NOT EXISTS items_date ON items(published_at DESC);
                CREATE INDEX IF NOT EXISTS items_url ON items(url);
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, value TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS source_status (source TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS checkpoints (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS observations (
                    id TEXT PRIMARY KEY, item_id TEXT NOT NULL, source TEXT NOT NULL,
                    external_id TEXT NOT NULL, binding TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL, value TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
                    UNIQUE(source,external_id,binding)
                );
                CREATE INDEX IF NOT EXISTS observations_item ON observations(item_id);
                CREATE INDEX IF NOT EXISTS observations_source ON observations(source,item_id);
                CREATE TABLE IF NOT EXISTS translations (
                    item_id TEXT NOT NULL, source_hash TEXT NOT NULL, model TEXT NOT NULL,
                    target_language TEXT NOT NULL, value TEXT NOT NULL,
                    PRIMARY KEY(item_id,source_hash,model,target_language)
                );
                CREATE TABLE IF NOT EXISTS translation_jobs (
                    id TEXT PRIMARY KEY, value TEXT NOT NULL, ids TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            if "source_hash" not in {column["name"] for column in db.execute("PRAGMA table_info(items)")}:
                db.execute("ALTER TABLE items ADD COLUMN source_hash TEXT NOT NULL DEFAULT ''")
            if "canonical_url" not in {column["name"] for column in db.execute("PRAGMA table_info(items)")}:
                db.execute("ALTER TABLE items ADD COLUMN canonical_url TEXT NOT NULL DEFAULT ''")
                for row in db.execute("SELECT id,url FROM items").fetchall():
                    db.execute("UPDATE items SET canonical_url=? WHERE id=?", (canonical_url(row["url"]), row["id"]))
            db.execute("CREATE INDEX IF NOT EXISTS items_canonical_url ON items(canonical_url)")
            for row in db.execute("SELECT id,value FROM items WHERE source_hash='' ").fetchall():
                db.execute("UPDATE items SET source_hash=? WHERE id=?", (source_hash(json.loads(row["value"])), row["id"]))
            if not db.execute("SELECT 1 FROM settings WHERE id=1").fetchone():
                db.execute("INSERT INTO settings VALUES(1,?)", (json.dumps(DEFAULT_SETTINGS),))
            # This local app runs one backend process. Resumable requests survive its restart.
            for row in db.execute("SELECT id,value FROM jobs").fetchall():
                job = json.loads(row[1])
                if job.get("status") == "running":
                    if job.get("request"):
                        job["status"] = "queued"
                        job["recovered"] = True
                        job.pop("lease_owner", None)
                        for progress in job.get("progress", []):
                            if progress.get("status") not in {"completed", "partial"}:
                                progress.update(status="pending", message="进程重启，等待继续采集")
                    else:
                        job["status"] = "failed"
                        job.setdefault("errors", []).append({"source": "system", "message": "旧版采集进程中断，请重新运行"})
                    db.execute("UPDATE jobs SET value=? WHERE id=?", (json.dumps(job), row[0]))
            for row in db.execute("SELECT id,value FROM translation_jobs").fetchall():
                job = json.loads(row[1])
                if job.get("status") == "running":
                    job["status"] = "failed"
                    job["failed"] = job["total"] - job["completed"]
                    job["errors"].append({"id": "", "message": "翻译进程中断，已完成译文仍在本机缓存"})
                    db.execute("UPDATE translation_jobs SET value=? WHERE id=?", (json.dumps(job), row[0]))
            # Seed provenance for existing installations without rewriting text or translations.
            for row in db.execute("SELECT * FROM items WHERE NOT EXISTS (SELECT 1 FROM observations o WHERE o.item_id=items.id)").fetchall():
                item = json.loads(row["value"])
                observation = self._observation(item, item.get("channels", ["search"])[0], "", row["collected_at"])
                observation["channels"] = item.get("channels", [])
                self._write_observation(db, row["id"], observation)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        def match(text, query):
            from .query import matches_query
            return int(matches_query(text or "", query or ""))
        db.create_function("query_matches", 2, match, deterministic=True)
        db.create_function("platform_engagement", 2, lambda source, score: min(1.0, math.log1p(max(0, float(score or 0))) / math.log1p({"x": 10000, "reddit": 1000, "hackernews": 500}.get(source, 1000))), deterministic=True)
        return db

    def settings(self):
        with self.connect() as db:
            saved = json.loads(db.execute("SELECT value FROM settings WHERE id=1").fetchone()[0])
        merged = deepcopy(DEFAULT_SETTINGS)
        merged.update(saved)
        return merged

    def save_settings(self, value):
        with self.connect() as db:
            db.execute("UPDATE settings SET value=? WHERE id=1", (json.dumps(value, ensure_ascii=False),))

    def ingest(self, post, channel: str, query: str = "", topic: str | None = None):
        return self.ingest_detailed(post, channel, query, topic)["added"]

    @staticmethod
    def _observation(post, channel, query, timestamp):
        source, external_id = post["source"], str(post.get("external_id") or post["url"])
        binding = str(post.get("feed_id") or post.get("account_id") or "")
        identity = hashlib.sha256(f"{source}:{external_id}:{binding}".encode()).hexdigest()[:24]
        fields = ("source_name", "author", "title", "url", "external_url", "feed_id", "feed_url", "guid", "provider_query", "content_kind", "language", "published_at", "updated_at")
        return {**{key: post[key] for key in fields if key in post}, "id": identity,
                "source": source, "external_id": external_id, "binding": binding,
                "channels": [channel], "channel": channel, "queries": [query] if query else [],
                "query": query, "collected_at": timestamp, "first_seen_at": timestamp, "last_seen_at": timestamp}

    @staticmethod
    def _write_observation(db, item_id, value):
        old = db.execute("SELECT value,first_seen_at FROM observations WHERE id=?", (value["id"],)).fetchone()
        if old:
            previous = json.loads(old["value"])
            value["first_seen_at"] = old["first_seen_at"]
            for key in ("channels", "queries"):
                value[key] = sorted(set(previous.get(key, []) + value.get(key, [])))
        db.execute("""INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            item_id=excluded.item_id,url=excluded.url,value=excluded.value,last_seen_at=excluded.last_seen_at""",
            (value["id"], item_id, value["source"], value["external_id"], value["binding"], value["url"],
             json.dumps(value, ensure_ascii=False), value["first_seen_at"], value["last_seen_at"]))

    def ingest_detailed(self, post, channel: str, query: str = "", topic: str | None = None):
        from .query import classify_topics, matches_query
        if not post.get("url") or not post.get("source"):
            raise ValueError("source and original URL are required")
        source = post["source"]
        external_id = str(post.get("external_id") or post["url"])
        identity = hashlib.sha256(f"{source}:{external_id}".encode()).hexdigest()[:24]
        current_time = now_iso()
        text = f"{post.get('title', '')} {post.get('content', '')}".lower()
        settings = self.settings()
        matched = [keyword for keyword in settings["keywords"] if matches_query(text, keyword)]
        if query and len(query) < 100 and matches_query(text, query):
            matched.append(query)
        topics = classify_topics(text)
        if channel == "search" and topic and topic != "all":
            topics.append(topic)
        value = {
            "id": identity, "external_id": external_id, "source": source,
            "source_name": post.get("source_name", source), "author": post.get("author", ""),
            "title": post.get("title", ""), "content": post.get("content", ""),
            "url": post["url"], "published_at": post.get("published_at"),
            "collected_at": current_time, "topics": sorted(set(topics + post.get("topics", []))),
            "matched_keywords": sorted(set(matched + post.get("matched_keywords", []))),
            "channels": sorted(set([channel] + post.get("channels", []))),
            "summary": post.get("summary") or (post.get("content") or post.get("title") or "")[:280],
            "summary_kind": post.get("summary_kind", "extractive"),
            "language": post.get("language") or ("zh" if any("\u4e00" <= c <= "\u9fff" for c in text) else "en"),
            "score": post.get("score", 0), "metrics": post.get("metrics") or {},
            "bookmarked": False, "is_read": False,
            "canonical_url": canonical_url(post["url"]),
        }
        for key in ("external_url", "source_url", "feed_id", "guid", "feed_url", "feed_name", "updated_at", "content_kind", "truncated", "provider_query", "references", "media", "account_id"):
            if key in post:
                value[key] = post[key]
        observation = self._observation(post, channel, query, current_time)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT items.* FROM observations JOIN items ON items.id=observations.item_id WHERE observations.id=?", (observation["id"],)).fetchone()
            if existing is None:
                existing = db.execute("SELECT * FROM items WHERE (source=? AND external_id=?) OR canonical_url=? ORDER BY CASE WHEN source=? AND external_id=? THEN 0 ELSE 1 END LIMIT 1",
                                      (source, external_id, value["canonical_url"], source, external_id)).fetchone()
            added = existing is None
            updated = False
            if existing:
                old = json.loads(existing["value"])
                legacy_feed = old["source"] == source == "rss" and not old.get("feed_id") and bool(post.get("feed_id"))
                primary = (old["source"] == source and old["external_id"] == external_id) or legacy_feed
                if not primary:
                    # The alternate source is an observation, never a replacement identity/body.
                    value = {**old, "collected_at": current_time}
                    value.pop("translation", None)
                    value.setdefault("canonical_url", existing["canonical_url"])
                else:
                    for key in ("external_url", "source_url", "feed_id", "guid", "feed_url", "content_kind", "references", "media", "account_id"):
                        if key not in value and key in old:
                            value[key] = old[key]
                    if old.get("content_kind") == "extracted_html" and value.get("content_kind") in {"feed_summary", "title_only"} and old["title"] == value["title"] and canonical_url(old["url"]) == value["canonical_url"]:
                        for key in ("content", "summary", "summary_kind", "content_kind", "content_extracted_at", "external_url", "truncated"):
                            if key in old:
                                value[key] = old[key]
                updated = primary and any(old.get(key) != value.get(key) for key in ("title", "content", "url", "score", "metrics", "external_url", "references"))
                value["id"] = old["id"]
                value["external_id"] = external_id if legacy_feed else old["external_id"]
                value["source"] = old["source"]
                for key in ("topics", "matched_keywords", "channels"):
                    incoming = topics + post.get("topics", []) if key == "topics" else matched + post.get("matched_keywords", []) if key == "matched_keywords" else [channel] + post.get("channels", [])
                    value[key] = sorted(set(old.get(key, []) + incoming))
                for key in ("bookmarked", "is_read"):
                    value[key] = old[key]
                same_original = old["title"] == value["title"] and old["content"] == value["content"]
                if old["summary_kind"] == "llm" and same_original:
                    value["summary"], value["summary_kind"] = old["summary"], "llm"
            db.execute("""INSERT INTO items(id,source,external_id,url,published_at,collected_at,value,bookmarked,is_read,source_hash,canonical_url)
                VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value,
                url=excluded.url,published_at=excluded.published_at,collected_at=excluded.collected_at,source_hash=excluded.source_hash,canonical_url=excluded.canonical_url""",
                (value["id"], value["source"], value["external_id"], value["url"], value["published_at"], current_time, json.dumps(value, ensure_ascii=False), value["bookmarked"], value["is_read"], source_hash(value), value["canonical_url"]))
            self._write_observation(db, value["id"], observation)
        return {"id": value["id"], "added": added, "updated": updated, "duplicate": not added and not updated}

    def decode(self, row):
        value = json.loads(row["value"])
        value["bookmarked"] = bool(row["bookmarked"])
        value["is_read"] = bool(row["is_read"])
        value["translation"] = self.get_translation(value["id"], source_hash(value), self.translation_model)
        value["canonical_url"] = row["canonical_url"]
        with self.connect() as db:
            value["observations"] = [json.loads(result[0]) for result in db.execute("SELECT value FROM observations WHERE item_id=? ORDER BY first_seen_at,id", (value["id"],))]
        return value

    def items(self, *, q="", topic=None, source=None, channel=None, bookmarked=None, limit=40, offset=0, sort="latest"):
        clauses, args = [], []
        if q:
            model_clause = " AND tr.model=?" if self.translation_model else ""
            clauses.append("(query_matches(COALESCE(json_extract(items.value,'$.title'),'') || ' ' || COALESCE(json_extract(items.value,'$.content'),'') || ' ' || COALESCE(json_extract(items.value,'$.author'),''),?) OR EXISTS (SELECT 1 FROM translations AS tr WHERE tr.item_id=items.id AND tr.source_hash=items.source_hash AND tr.target_language='zh'" + model_clause + " AND query_matches(COALESCE(json_extract(tr.value,'$.title'),'') || ' ' || COALESCE(json_extract(tr.value,'$.content'),'') || ' ' || COALESCE(json_extract(tr.value,'$.summary'),''),?)))")
            args.append(q)
            if self.translation_model:
                args.append(self.translation_model)
            args.append(q)
        if source:
            clauses.append("(source=? OR EXISTS (SELECT 1 FROM observations o WHERE o.item_id=items.id AND o.source=?))")
            args += [source, source]
        for key, field in [(topic if topic != "all" else None, "topics"), (channel, "channels")]:
            if key:
                clauses.append(f"EXISTS (SELECT 1 FROM json_each(items.value,'$.{field}') AS tag WHERE tag.value=?)")
                args.append(key)
        if bookmarked is not None:
            clauses.append("bookmarked=?")
            args.append(int(bookmarked))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        ordering = "COALESCE(published_at,collected_at) DESC,collected_at DESC"
        if sort == "relevance":
            # Compare engagement on a log scale within its platform; it is not evidence quality.
            ordering = "json_array_length(json_extract(items.value,'$.matched_keywords')) DESC,platform_engagement(source,COALESCE(json_extract(items.value,'$.score'),0)) DESC," + ordering
        with self.connect() as db:
            total = db.execute("SELECT COUNT(*) FROM items" + where, args).fetchone()[0]
            rows = db.execute("SELECT * FROM items" + where + " ORDER BY " + ordering + " LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
        return {"items": [self.decode(row) for row in rows], "total": total, "limit": limit, "offset": offset}

    def get_item(self, identity):
        with self.connect() as db:
            row = db.execute("SELECT * FROM items WHERE id=?", (identity,)).fetchone()
        return self.decode(row) if row else None

    def update_item(self, identity, updates, *, expected_item=None):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM items WHERE id=?", (identity,)).fetchone()
            if not row:
                return None
            item = self.decode(row)
            if expected_item is not None and (source_hash(item) != source_hash(expected_item) or any(item.get(key) != expected_item.get(key) for key in ("url", "external_url"))):
                raise ItemVersionConflict("来源已更新，请重新读取公开正文；新内容已保留")
            item.update(updates)
            if "content" in updates or "title" in updates:
                from .query import classify_topics, matches_query
                text = item.get("title", "") + " " + item.get("content", "")
                item["topics"] = sorted(set(item.get("topics", []) + classify_topics(text)))
                item["matched_keywords"] = sorted(set(item.get("matched_keywords", []) + [word for word in self.settings()["keywords"] if matches_query(text, word)]))
            stored = {key: value for key, value in item.items() if key != "translation"}
            db.execute("UPDATE items SET value=?,bookmarked=?,is_read=?,source_hash=? WHERE id=?", (json.dumps(stored, ensure_ascii=False), int(item["bookmarked"]), int(item["is_read"]), source_hash(item), identity))
        return self.get_item(identity)

    def get_translation(self, identity, digest, model=None):
        model_clause = " AND model=?" if model else ""
        arguments = [identity, digest] + ([model] if model else [])
        with self.connect() as db:
            row = db.execute("SELECT value FROM translations WHERE item_id=? AND source_hash=? AND target_language='zh'" + model_clause + " ORDER BY json_extract(value,'$.translated_at') DESC LIMIT 1", arguments).fetchone()
        return json.loads(row[0]) if row else None

    def save_translation(self, identity, digest, model, value):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM items WHERE id=?", (identity,)).fetchone()
            if not row or source_hash(json.loads(row[0])) != digest:
                return False
            db.execute("INSERT INTO translations VALUES(?,?,?,?,?) ON CONFLICT(item_id,source_hash,model,target_language) DO UPDATE SET value=excluded.value", (identity, digest, model, "zh", json.dumps(value, ensure_ascii=False)))
        return True

    def save_translation_job(self, job, ids=None):
        with self.connect() as db:
            db.execute("INSERT INTO translation_jobs VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value", (job["id"], json.dumps(job, ensure_ascii=False), json.dumps(ids or []), now_iso()))

    def get_translation_job(self, identity):
        with self.connect() as db:
            row = db.execute("SELECT value FROM translation_jobs WHERE id=?", (identity,)).fetchone()
        return json.loads(row[0]) if row else None

    def translation_job_ids(self, identity):
        with self.connect() as db:
            row = db.execute("SELECT ids FROM translation_jobs WHERE id=?", (identity,)).fetchone()
        return json.loads(row[0]) if row else []

    def overview(self):
        with self.connect() as db:
            totals = db.execute("SELECT count(*),sum(bookmarked),sum(1-is_read) FROM items").fetchone()
            channels = {channel: db.execute("SELECT COUNT(*) FROM items WHERE EXISTS(SELECT 1 FROM json_each(json_extract(items.value,'$.channels')) WHERE value=?)", (channel,)).fetchone()[0] for channel in ["search", "following", "recommended"]}
            topics = []
            for topic in TOPICS:
                count = totals[0] if topic["id"] == "all" else db.execute("SELECT COUNT(*) FROM items WHERE EXISTS(SELECT 1 FROM json_each(json_extract(items.value,'$.topics')) WHERE value=?)", (topic["id"],)).fetchone()[0]
                topics.append({**topic, "count": count})
        return {"topics": topics, "keywords": self.settings()["keywords"], "counts": {"total": totals[0], "bookmarked": totals[1] or 0, "unread": totals[2] or 0, **channels}}

    def save_job(self, job):
        with self.connect() as db:
            db.execute("INSERT INTO jobs VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value", (job["id"], json.dumps(job, ensure_ascii=False), job.get("created_at", now_iso())))

    def get_job(self, identity):
        with self.connect() as db:
            row = db.execute("SELECT value FROM jobs WHERE id=?", (identity,)).fetchone()
        return json.loads(row[0]) if row else None

    def status(self, source, value=None):
        with self.connect() as db:
            if value is not None:
                previous = db.execute("SELECT value FROM source_status WHERE source=?", (source,)).fetchone()
                value = {**(json.loads(previous[0]) if previous else {}), **value}
                db.execute("INSERT INTO source_status VALUES(?,?) ON CONFLICT(source) DO UPDATE SET value=excluded.value", (source, json.dumps(value, ensure_ascii=False)))
            row = db.execute("SELECT value FROM source_status WHERE source=?", (source,)).fetchone()
        return json.loads(row[0]) if row else None

    def get_checkpoint(self, key: str):
        with self.connect() as db:
            row = db.execute("SELECT value FROM checkpoints WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_checkpoint(self, key: str, value: dict):
        with self.connect() as db:
            db.execute("INSERT INTO checkpoints VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                       (key, json.dumps(value, ensure_ascii=False), now_iso()))

    def active_jobs(self):
        with self.connect() as db:
            rows = db.execute("SELECT value FROM jobs WHERE json_extract(value,'$.status') IN ('queued','running') ORDER BY created_at").fetchall()
        return [json.loads(row[0]) for row in rows]

    def enqueue_job(self, job: dict, max_pending: int = 20):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT value FROM jobs WHERE json_extract(value,'$.status') IN ('queued','running')").fetchall()
            for row in rows:
                active = json.loads(row[0])
                if active.get("fingerprint") == job["fingerprint"]:
                    return active
            if len(rows) >= max_pending:
                raise ValueError("采集队列已满，请等待当前任务完成")
            db.execute("INSERT INTO jobs VALUES(?,?,?)", (job["id"], json.dumps(job, ensure_ascii=False), job["created_at"]))
        return job

    def claim_job(self, owner: str):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id,value FROM jobs WHERE json_extract(value,'$.status')='queued' ORDER BY created_at,id LIMIT 1").fetchone()
            if row is None:
                return None
            job = json.loads(row["value"])
            job.update(status="running", lease_owner=owner, started_at=job.get("started_at") or now_iso())
            db.execute("UPDATE jobs SET value=? WHERE id=? AND json_extract(value,'$.status')='queued'", (json.dumps(job, ensure_ascii=False), row["id"]))
        return job
