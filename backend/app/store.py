from __future__ import annotations

import hashlib
import json
import sqlite3
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from .config import DEFAULT_SETTINGS, TOPICS, TOPIC_TERMS
from .translation import source_hash


def now_iso():
    return datetime.now(timezone.utc).isoformat()


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
            for row in db.execute("SELECT id,value FROM items WHERE source_hash='' ").fetchall():
                db.execute("UPDATE items SET source_hash=? WHERE id=?", (source_hash(json.loads(row["value"])), row["id"]))
            if not db.execute("SELECT 1 FROM settings WHERE id=1").fetchone():
                db.execute("INSERT INTO settings VALUES(1,?)", (json.dumps(DEFAULT_SETTINGS),))
            # An interrupted process must not leave a permanently running job.
            for row in db.execute("SELECT id,value FROM jobs").fetchall():
                job = json.loads(row[1])
                if job.get("status") == "running":
                    job["status"] = "failed"
                    job["errors"].append({"source": "system", "message": "采集进程中断，请重新运行"})
                    db.execute("UPDATE jobs SET value=? WHERE id=?", (json.dumps(job), row[0]))
            for row in db.execute("SELECT id,value FROM translation_jobs").fetchall():
                job = json.loads(row[1])
                if job.get("status") == "running":
                    job["status"] = "failed"
                    job["failed"] = job["total"] - job["completed"]
                    job["errors"].append({"id": "", "message": "翻译进程中断，已完成译文仍在本机缓存"})
                    db.execute("UPDATE translation_jobs SET value=? WHERE id=?", (json.dumps(job), row[0]))

    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
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
        if not post.get("url") or not post.get("source"):
            raise ValueError("source and original URL are required")
        source = post["source"]
        external_id = str(post.get("external_id") or post["url"])
        identity = hashlib.sha256(f"{source}:{external_id}".encode()).hexdigest()[:24]
        current_time = now_iso()
        text = f"{post.get('title', '')} {post.get('content', '')}".lower()
        settings = self.settings()
        matched = [keyword for keyword in settings["keywords"] if keyword.casefold() in text.casefold()]
        if query and len(query) < 100 and query.casefold() in text.casefold():
            matched.append(query)
        topics = [name for name, terms in TOPIC_TERMS.items() if any(term in text for term in terms)]
        if topic and topic != "all":
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
        }
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM items WHERE (source=? AND external_id=?) OR url=? LIMIT 1", (source, external_id, value["url"])).fetchone()
            added = existing is None
            if existing:
                old = self.decode(existing)
                value["id"] = old["id"]
                value["external_id"] = old["external_id"]
                value["source"] = old["source"]
                for key in ("topics", "matched_keywords", "channels"):
                    value[key] = sorted(set(old[key] + value[key]))
                for key in ("bookmarked", "is_read"):
                    value[key] = old[key]
                same_original = old["title"] == value["title"] and old["content"] == value["content"]
                if old["summary_kind"] == "llm" and same_original:
                    value["summary"], value["summary_kind"] = old["summary"], "llm"
                if (old["source"] != source or old["external_id"] != external_id) and len(old["content"]) > len(value["content"]):
                    value["content"] = old["content"]
            db.execute("""INSERT INTO items(id,source,external_id,url,published_at,collected_at,value,bookmarked,is_read,source_hash)
                VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value,
                url=excluded.url,published_at=excluded.published_at,collected_at=excluded.collected_at,source_hash=excluded.source_hash""",
                (value["id"], value["source"], value["external_id"], value["url"], value["published_at"], current_time, json.dumps(value, ensure_ascii=False), value["bookmarked"], value["is_read"], source_hash(value)))
        return added

    def decode(self, row):
        value = json.loads(row["value"])
        value["bookmarked"] = bool(row["bookmarked"])
        value["is_read"] = bool(row["is_read"])
        value["translation"] = self.get_translation(value["id"], source_hash(value), self.translation_model)
        return value

    def items(self, *, q="", topic=None, source=None, channel=None, bookmarked=None, limit=40, offset=0, sort="latest"):
        clauses, args = [], []
        if q:
            pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            model_clause = " AND tr.model=?" if self.translation_model else ""
            clauses.append("(json_extract(items.value,'$.title') LIKE ? ESCAPE '\\' OR json_extract(items.value,'$.content') LIKE ? ESCAPE '\\' OR json_extract(items.value,'$.author') LIKE ? ESCAPE '\\' OR EXISTS (SELECT 1 FROM translations AS tr WHERE tr.item_id=items.id AND tr.source_hash=items.source_hash AND tr.target_language='zh'" + model_clause + " AND (json_extract(tr.value,'$.title') LIKE ? ESCAPE '\\' OR json_extract(tr.value,'$.content') LIKE ? ESCAPE '\\' OR json_extract(tr.value,'$.summary') LIKE ? ESCAPE '\\')))")
            args += [pattern] * 3
            if self.translation_model:
                args.append(self.translation_model)
            args += [pattern] * 3
        if source:
            clauses.append("source=?")
            args.append(source)
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
            ordering = "json_array_length(json_extract(items.value,'$.matched_keywords')) DESC,COALESCE(json_extract(items.value,'$.score'),0) DESC," + ordering
        with self.connect() as db:
            total = db.execute("SELECT COUNT(*) FROM items" + where, args).fetchone()[0]
            rows = db.execute("SELECT * FROM items" + where + " ORDER BY " + ordering + " LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
        return {"items": [self.decode(row) for row in rows], "total": total, "limit": limit, "offset": offset}

    def get_item(self, identity):
        with self.connect() as db:
            row = db.execute("SELECT * FROM items WHERE id=?", (identity,)).fetchone()
        return self.decode(row) if row else None

    def update_item(self, identity, updates):
        with self.connect() as db:
            row = db.execute("SELECT * FROM items WHERE id=?", (identity,)).fetchone()
            if not row:
                return None
            item = self.decode(row)
            item.update(updates)
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
                db.execute("INSERT INTO source_status VALUES(?,?) ON CONFLICT(source) DO UPDATE SET value=excluded.value", (source, json.dumps(value, ensure_ascii=False)))
            row = db.execute("SELECT value FROM source_status WHERE source=?", (source,)).fetchone()
        return json.loads(row[0]) if row else None
