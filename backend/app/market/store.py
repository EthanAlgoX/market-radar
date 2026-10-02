from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from .models import MAX_INSTRUMENTS, WINDOW, fingerprint, instrument_spec, now_iso, quality_summary


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class MarketStore:
    """Independent local database; one process owns the recoverable worker."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS instruments (
                    id TEXT PRIMARY KEY, market TEXT NOT NULL, symbol TEXT NOT NULL,
                    value TEXT NOT NULL, UNIQUE(market,symbol));
                CREATE TABLE IF NOT EXISTS candles (
                    instrument_id TEXT NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
                    time TEXT NOT NULL, value TEXT NOT NULL, source_hash TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(instrument_id,time));
                CREATE TABLE IF NOT EXISTS candle_revisions (
                    instrument_id TEXT NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
                    time TEXT NOT NULL, revision INTEGER NOT NULL, value TEXT NOT NULL,
                    PRIMARY KEY(instrument_id,time,revision));
                CREATE TABLE IF NOT EXISTS analyses (
                    instrument_id TEXT PRIMARY KEY REFERENCES instruments(id) ON DELETE CASCADE,
                    value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS signals (
                    id TEXT PRIMARY KEY, instrument_id TEXT NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
                    bar_time TEXT NOT NULL, source_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
                    revision INTEGER NOT NULL DEFAULT 1, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS signal_revisions (
                    id TEXT NOT NULL, revision INTEGER NOT NULL,
                    instrument_id TEXT NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
                    value TEXT NOT NULL, PRIMARY KEY(id,revision));
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, value TEXT NOT NULL);
            """)
            for row in db.execute("SELECT id,value FROM jobs").fetchall():
                job = json.loads(row["value"])
                if job["status"] == "running":
                    job.update(status="queued", recovered=True)
                    for progress in job["progress"]:
                        if progress["status"] not in {"completed", "partial", "skipped"}:
                            progress.update(status="pending", message="本地进程重启，等待恢复")
                    db.execute("UPDATE jobs SET value=? WHERE id=?", (encode(job), job["id"]))

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def watchlist(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT value FROM instruments ORDER BY rowid")]

    def get_instrument(self, identity):
        with self.connect() as db:
            row = db.execute("SELECT value FROM instruments WHERE id=?", (identity,)).fetchone()
        return json.loads(row[0]) if row else None

    def add(self, market, symbol):
        value = instrument_spec(market, symbol)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM instruments WHERE market=? AND symbol=?", (market, value["symbol"])).fetchone()
            if row:
                return json.loads(row[0])
            if db.execute("SELECT COUNT(*) FROM instruments").fetchone()[0] >= MAX_INSTRUMENTS:
                raise ValueError("自选列表最多 20 个标的，请先移除一个")
            value.update(id=uuid.uuid4().hex, status="idle", message="已添加；点击刷新后采集", count=0,
                         created_at=now_iso(), last_attempt_at=None, last_success_at=None, last_bar_at=None,
                         quality=quality_summary([]))
            db.execute("INSERT INTO instruments VALUES(?,?,?,?)", (value["id"], market, value["symbol"], encode(value)))
        return value

    def delete(self, identity):
        with self.connect() as db:
            return bool(db.execute("DELETE FROM instruments WHERE id=?", (identity,)).rowcount)

    def update_instrument(self, identity, updates):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM instruments WHERE id=?", (identity,)).fetchone()
            if not row:
                return None
            value = json.loads(row[0])
            value.update(updates)
            db.execute("UPDATE instruments SET value=? WHERE id=?", (encode(value), identity))
        return value

    def candles(self, identity, limit=WINDOW):
        with self.connect() as db:
            rows = db.execute("SELECT value FROM candles WHERE instrument_id=? ORDER BY time DESC LIMIT ?", (identity, limit)).fetchall()
        return [json.loads(row[0]) for row in reversed(rows)]

    def _reconcile_gaps(self, db, identity, spec, incoming):
        """Check the stored/fetched seam and any successor of a filled gap.

        A finite provider response cannot see its stored predecessor. Also a
        missing row in that response may already be in the database. Evaluate
        the merged local sequence, including one neighbour on each side, and
        persist any gap-quality changes with their normal data revisions.
        """
        from .providers import finish_candle

        incoming = {bar["time"]: dict(bar) for bar in incoming}
        if not incoming:
            return []
        first, last = min(incoming), max(incoming)
        existing = {row["time"]: json.loads(row["value"]) for row in db.execute(
            "SELECT time,value FROM candles WHERE instrument_id=? AND time>=? AND time<=?",
            (identity, first, last))}
        for condition, boundary, order in (("<", first, "DESC"), (">", last, "ASC")):
            row = db.execute(f"SELECT time,value FROM candles WHERE instrument_id=? AND time{condition}? ORDER BY time {order} LIMIT 1",
                             (identity, boundary)).fetchone()
            if row:
                existing[row["time"]] = json.loads(row["value"])
        merged = {**existing, **incoming}
        ordered = [merged[key] for key in sorted(merged)]
        calendar = None
        if spec["market"] != "crypto":
            try:
                import exchange_calendars as xcals
                calendar = xcals.get_calendar({"us": "XNYS", "hk": "XHKG", "cn": "XSHG"}[spec["market"]],
                                              start=ordered[0]["trading_date"],
                                              end=(datetime.fromisoformat(ordered[-1]["trading_date"]) + timedelta(days=7)).date().isoformat())
            except Exception:
                pass
        writes = dict(incoming)
        for index, bar in enumerate(ordered):
            # The untouched leading predecessor has no predecessor here; this
            # bounded check cannot establish anything new about its own gap.
            if index == 0 and bar["time"] not in incoming:
                continue
            value = dict(bar)
            flags = set(value.get("quality", []))
            if index == 0:
                if "gap_before" in existing.get(bar["time"], {}).get("quality", []):
                    flags.add("gap_before")
            else:
                previous = ordered[index - 1]
                try:
                    if spec["market"] == "crypto":
                        contiguous = (datetime.fromisoformat(value["time"]) - datetime.fromisoformat(previous["time"]) == timedelta(hours=1)
                                      and previous["end_time"] == value["time"])
                    else:
                        if calendar is None:
                            raise ValueError("calendar unavailable")
                        import pandas as pd
                        prev_session, session = pd.Timestamp(previous["trading_date"]), pd.Timestamp(value["trading_date"])
                        if not calendar.is_session(prev_session) or not calendar.is_session(session):
                            raise ValueError("non-trading session")
                        contiguous = calendar.next_session(prev_session) == session
                    flags.discard("gap_before")
                    if not contiguous:
                        flags.add("gap_before")
                except Exception:
                    flags.add("calendar_unconfirmed" if spec["market"] != "crypto" else "invalid_interval")
            value["quality"] = sorted(flags)
            value = finish_candle(spec, value)
            if bar["time"] in incoming or value["source_hash"] != existing[bar["time"]]["source_hash"]:
                writes[bar["time"]] = value
        return [writes[key] for key in sorted(writes)]

    def ingest(self, identity, candles):
        if len({candle["time"] for candle in candles}) != len(candles):
            raise ValueError("拒绝重复时间戳，未覆盖原有行情")
        new, updated, changed_times = 0, 0, []
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            instrument = db.execute("SELECT value FROM instruments WHERE id=?", (identity,)).fetchone()
            if not instrument:
                return {"new": 0, "updated": 0, "deleted": True, "changed_times": []}
            spec = json.loads(instrument[0])
            incoming_window = candles[-(WINDOW if spec["market"] == "crypto" else WINDOW + 60):]
            for incoming in incoming_window:
                if any(incoming.get(key) != spec[key] for key in ("provider", "symbol", "interval", "adjustment", "session", "currency", "timezone", "volume_unit")):
                    raise ValueError("拒绝将不同来源或口径拼入同一行情序列")
            for incoming in self._reconcile_gaps(db, identity, spec, incoming_window):
                old = db.execute("SELECT * FROM candles WHERE instrument_id=? AND time=?", (identity, incoming["time"])).fetchone()
                value = dict(incoming)
                revision = old["revision"] if old else 1
                if old and old["source_hash"] != value["source_hash"]:
                    db.execute("INSERT OR IGNORE INTO candle_revisions VALUES(?,?,?,?)", (identity, value["time"], revision, old["value"]))
                    revision += 1
                    updated += 1
                    changed_times.append(value["time"])
                elif not old:
                    new += 1
                value["revision"] = revision
                db.execute("INSERT INTO candles VALUES(?,?,?,?,?) ON CONFLICT(instrument_id,time) DO UPDATE SET value=excluded.value,source_hash=excluded.source_hash,revision=excluded.revision",
                           (identity, value["time"], encode(value), value["source_hash"], revision))
        return {"new": new, "updated": updated, "deleted": False, "changed_times": changed_times}

    def save_analysis(self, identity, analysis, candles, *, changed_times=None):
        if not candles:
            return
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM instruments WHERE id=?", (identity,)).fetchone():
                return
            from .signals import RULES
            min_bars = {rule["id"]: rule["min_bars"] for rule in RULES}
            current_ids = {signal["id"] for signal in analysis.get("signals", [])}
            # Only invalidate inside this evaluated window; older history remains intact.
            for old in db.execute("SELECT * FROM signals WHERE instrument_id=? AND bar_time>=? AND bar_time<=? AND active=1",
                                  (identity, candles[0]["time"], candles[-1]["end_time"])).fetchall():
                if old["id"] not in current_ids:
                    value = json.loads(old["value"])
                    needed = min_bars.get(value.get("rule_id"), 1)
                    if len(candles) < needed or old["bar_time"] < candles[needed - 1]["time"]:
                        # A sliding fetch window is not evidence that a historical event became false.
                        if any(candles[0]["time"] <= changed <= old["bar_time"] for changed in (changed_times or [])):
                            value.update(pending_revalidation=True, revalidation_message="历史来源已修订，但窗口不足以重新确认该旧信号")
                            db.execute("UPDATE signals SET value=? WHERE id=?", (encode(value), old["id"]))
                        continue
                    db.execute("INSERT OR IGNORE INTO signal_revisions VALUES(?,?,?,?)", (old["id"], old["revision"], identity, old["value"]))
                    value.update(active=False, revised=True, revised_at=now_iso(), revision_reason="来源修订或质量变化后不再确认", data_revision=old["revision"] + 1)
                    db.execute("UPDATE signals SET active=0,revision=?,value=? WHERE id=?", (old["revision"] + 1, encode(value), old["id"]))
            for incoming in analysis.get("signals", []):
                old = db.execute("SELECT * FROM signals WHERE id=?", (incoming["id"],)).fetchone()
                if old and old["source_hash"] == incoming["source_hash"] and old["active"]:
                    saved = json.loads(old["value"])
                    if saved.get("pending_revalidation"):
                        saved.update(pending_revalidation=False, revalidated_at=now_iso())
                        db.execute("UPDATE signals SET value=? WHERE id=?", (encode(saved), old["id"]))
                    continue
                value = dict(incoming)
                revision = old["revision"] + 1 if old else 1
                if old:
                    db.execute("INSERT OR IGNORE INTO signal_revisions VALUES(?,?,?,?)", (old["id"], old["revision"], identity, old["value"]))
                value.update(active=True, revised=bool(old), revised_at=now_iso() if old else None, data_revision=revision, pending_revalidation=False)
                db.execute("INSERT INTO signals VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET source_hash=excluded.source_hash,active=1,revision=excluded.revision,value=excluded.value",
                           (value["id"], identity, value.get("bar_time", value.get("bar_start", "")), value["source_hash"], 1, revision, encode(value)))
            db.execute("INSERT INTO analyses VALUES(?,?) ON CONFLICT(instrument_id) DO UPDATE SET value=excluded.value", (identity, encode({k: v for k, v in analysis.items() if k != "signals"})))

    def analysis(self, identity):
        with self.connect() as db:
            row = db.execute("SELECT value FROM analyses WHERE instrument_id=?", (identity,)).fetchone()
            signals = [json.loads(item[0]) for item in db.execute("SELECT value FROM signals WHERE instrument_id=? AND active=1 ORDER BY bar_time DESC LIMIT 20", (identity,))]
            revised = db.execute("SELECT COUNT(*) FROM signals WHERE instrument_id=? AND active=0", (identity,)).fetchone()[0]
        result = json.loads(row[0]) if row else {"status": "empty", "message": "尚未采集行情", "indicators": [], "warmup": {}, "latest": None}
        return {**result, "signals": signals, "invalidated_signal_count": revised}

    def enqueue(self, ids):
        ids = sorted(set(ids))
        if not ids:
            raise ValueError("请先添加自选标的")
        stamp = now_iso()
        value = {"id": uuid.uuid4().hex, "status": "queued", "created_at": stamp, "started_at": None,
                 "completed_at": None, "request": {"ids": ids}, "fingerprint": fingerprint({"ids": ids}),
                 "progress": [], "errors": [], "added": 0, "updated": 0, "total": 0, "recovered": False}
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            active = [json.loads(row[0]) for row in db.execute("SELECT value FROM jobs WHERE json_extract(value,'$.status') IN ('queued','running')")]
            existing = next((job for job in active if job["fingerprint"] == value["fingerprint"]), None)
            if existing:
                return existing
            if len(active) >= 5:
                raise ValueError("行情任务队列已满，请等待现有任务完成")
            for identity in ids:
                row = db.execute("SELECT value FROM instruments WHERE id=?", (identity,)).fetchone()
                if not row:
                    raise ValueError("自选标的不存在或已删除")
                spec = json.loads(row[0])
                value["progress"].append({"instrument_id": identity, "symbol": spec["symbol"], "provider": spec["provider"],
                                          "status": "pending", "count": 0, "new": 0, "updated": 0, "message": "等待采集"})
            db.execute("INSERT INTO jobs VALUES(?,?,?)", (value["id"], stamp, encode(value)))
        return value

    def save_job(self, job):
        with self.connect() as db:
            db.execute("UPDATE jobs SET value=? WHERE id=?", (encode(job), job["id"]))

    def get_job(self, identity):
        with self.connect() as db:
            row = db.execute("SELECT value FROM jobs WHERE id=?", (identity,)).fetchone()
        return json.loads(row[0]) if row else None

    def active_jobs(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT value FROM jobs WHERE json_extract(value,'$.status') IN ('queued','running') ORDER BY created_at")]

    def claim(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM jobs WHERE json_extract(value,'$.status')='queued' ORDER BY created_at LIMIT 1").fetchone()
            if not row:
                return None
            job = json.loads(row[0])
            job.update(status="running", started_at=job["started_at"] or now_iso())
            db.execute("UPDATE jobs SET value=? WHERE id=?", (encode(job), job["id"]))
        return job
