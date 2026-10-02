from __future__ import annotations

import asyncio
import contextlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import MAX_INSTRUMENTS, PRESETS, WINDOW, now_iso, quality_summary
from .providers import PROVIDERS, ProviderError, PublicMarketProviders, freshness, usable_closed_candles
from .store import MarketStore


class MarketService:
    def __init__(self, data_dir: Path, providers=None, news_store=None):
        self.store = MarketStore(Path(data_dir) / "market-radar-market.sqlite3")
        self.providers = providers or PublicMarketProviders()
        self.news_store = news_store
        self.worker_task = None
        self.wake = asyncio.Event()
        self.instrument_budget = 65
        self.job_budget = 240

    def start_workers(self):
        if self.worker_task is None or self.worker_task.done():
            self.worker_task = asyncio.create_task(self.worker())

    async def shutdown(self):
        if self.worker_task is not None:
            self.worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.worker_task
            self.worker_task = None

    def add_watchlist(self, market, symbol):
        return self.store.add(market, symbol)

    def delete_watchlist(self, identity):
        return self.store.delete(identity)

    def new_job(self, ids=None):
        selected = ids or [row["id"] for row in self.store.watchlist()]
        job = self.store.enqueue(selected)
        self.wake.set()
        return job

    def get_job(self, identity):
        return self.store.get_job(identity)

    def overview(self):
        from .signals import RULES
        watchlist = self.store.watchlist()
        providers = []
        for definition in PROVIDERS:
            rows = [row for row in watchlist if row["provider"] == definition["id"]]
            attempted = [row for row in rows if row.get("last_attempt_at")]
            latest = max(attempted, key=lambda row: row["last_attempt_at"]) if attempted else None
            providers.append({**definition, "status": latest["status"] if latest else "idle",
                              "message": latest["message"] if latest else "尚未访问；添加自选后手动刷新",
                              "last_attempt_at": latest.get("last_attempt_at") if latest else None,
                              "last_success_at": max((row.get("last_success_at") or "" for row in rows), default="") or None})
        active = self.store.active_jobs()
        return {"watchlist": watchlist, "providers": providers, "rules": RULES,
                "presets": [{k: v for k, v in row.items() if k != "aliases"} for row in PRESETS],
                "limits": {"max_instruments": MAX_INSTRUMENTS, "window": WINDOW, "workers": 1, "job_budget_seconds": self.job_budget},
                "active_job": active[0] if active else None}

    def related_news(self, instrument, candles):
        if self.news_store is None or not candles or not instrument.get("aliases"):
            return []
        # No bare numeric stock-code matching. Fixed company names or whole ticker words only.
        aliases = instrument["aliases"]
        try:
            target = datetime.fromisoformat(candles[-1]["end_time"])
            result = []
            for item in self.news_store.items(q=instrument["news_query"], limit=100)["items"]:
                value = item.get("published_at")
                if not value:
                    continue
                published = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if published.tzinfo is None:
                    continue
                if not target - timedelta(days=3) <= published <= target + timedelta(days=1):
                    continue
                text = " ".join(item.get(key, "") or "" for key in ("title", "content", "author"))
                if not any((re.search(r"(?<![A-Za-z0-9_])" + re.escape(alias) + r"(?![A-Za-z0-9_])", text, re.I)
                            if alias.isascii() else alias in text) for alias in aliases):
                    continue
                # Existing decoded Post carries source_hash/translations for the normal reader actions.
                result.append(dict(item))
                result[-1].update(relation="同期实体相关资讯，未证明价格变化因果", window="bar close -3d / +1d")
                if len(result) == 8:
                    break
            return result
        except (ValueError, TypeError, KeyError):
            return []

    def snapshot(self, identity, limit=WINDOW):
        instrument = self.store.get_instrument(identity)
        if instrument is None:
            return None
        candles = self.store.candles(identity, limit)
        analysis = self.store.analysis(identity)
        quality = quality_summary(candles)
        closed = usable_closed_candles(candles)
        raw_closed = [bar for bar in candles if bar.get("closed")]
        freshness_state = freshness(instrument, candles)
        stale = freshness_state["stale"] or instrument["status"] == "error"
        coverage = {"count": len(candles), "first_bar_at": candles[0]["time"] if candles else None,
                    "last_bar_at": candles[-1]["time"] if candles else None,
                    "last_closed_bar_at": closed[-1]["end_time"] if closed else None,
                    "last_raw_closed_bar_at": raw_closed[-1]["end_time"] if raw_closed else None,
                    "received_at": max((bar["received_at"] for bar in candles), default=None),
                    "interval": instrument["interval"], "window": WINDOW, "history_complete": False,
                    **freshness_state, "stale": stale}
        signal_analysis = {key: value for key, value in analysis.items() if key not in {"signals", "indicators"}}
        if stale and candles:
            signal_analysis.update(status="stale", message="当前数据未确认新鲜；保留历史信号，不能视为本次新触发")
        signals = [{**signal, "is_stale": stale, "historical": True} for signal in analysis["signals"]
                   if candles and candles[0]["time"] <= signal.get("bar_time", "") <= candles[-1]["end_time"]]
        selected_times = {bar["time"] for bar in candles}
        return {"instrument": instrument, "candles": candles, "quality": quality, "coverage": coverage,
                "signals": signals, "indicators": [point for point in analysis.get("indicators", []) if point["time"] in selected_times], "signal_analysis": signal_analysis,
                "related_news": self.related_news(instrument, candles), "source_url": instrument.get("source_url"),
                "status": instrument["status"], "message": instrument["message"]}

    async def worker(self):
        while True:
            job = self.store.claim()
            if job is None:
                self.wake.clear()
                # Persistent queue is authoritative; the timeout closes admission/wakeup races.
                try:
                    await asyncio.wait_for(self.wake.wait(), timeout=.5)
                except asyncio.TimeoutError:
                    pass
                continue
            await self.run_job(job)

    async def run_job(self, job):
        from .signals import compute_signals
        deadline = asyncio.get_running_loop().time() + self.job_budget
        for progress in job["progress"]:
            if progress["status"] in {"completed", "partial", "skipped"}:
                continue
            identity = progress["instrument_id"]
            instrument = self.store.get_instrument(identity)
            job["errors"] = [error for error in job["errors"] if error["instrument_id"] != identity]
            if instrument is None:
                progress.update(status="skipped", message="自选已删除，未采集")
                self.store.save_job(job)
                continue
            progress.update(status="running", message="正在取得有限行情窗口")
            self.store.update_instrument(identity, {"last_attempt_at": now_iso(), "status": "running", "message": "行情任务采集中"})
            self.store.save_job(job)
            try:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise ProviderError("本次行情任务时间预算已耗尽，请重新刷新未完成标的")
                result = await asyncio.wait_for(self.providers.fetch(instrument), timeout=min(self.instrument_budget, remaining))
                if not result.candles:
                    raise ProviderError("来源返回空行情；已保留此前数据")
                changes = self.store.ingest(identity, result.candles)
                if changes["deleted"]:
                    progress.update(status="skipped", message="采集期间自选已删除，未保存")
                    self.store.save_job(job)
                    continue
                # Stocks refresh warmup with their view to catch vendor revisions;
                # crypto can reuse stored context behind its finite hourly fetch.
                candles = self.store.candles(identity, limit=WINDOW + 60)
                analysis = compute_signals(candles, emitted_at=now_iso(), limit=1000)
                self.store.save_analysis(identity, analysis, candles, changed_times=changes["changed_times"])
                quality = quality_summary(candles[-WINDOW:])
                partial = bool(quality["flags"])
                state = "partial" if partial else "available"
                message = "取得行情但存在质量标记；信号只用合格闭合窗口" if partial else result.message
                self.store.update_instrument(identity, {"status": state, "message": message,
                    "last_success_at": now_iso(), "last_bar_at": result.candles[-1]["time"],
                    "count": min(WINDOW, len(candles)), "quality": quality})
                progress.update(status="partial" if partial else "completed", count=len(result.candles),
                                new=changes["new"], updated=changes["updated"], message=message)
            except asyncio.CancelledError:
                # Keep a resumable running request on disk; the next process requeues it.
                raise
            except Exception as exc:
                message = str(exc) if isinstance(exc, ProviderError) else "行情请求超时，旧数据已保留" if isinstance(exc, TimeoutError) else "行情处理未完成，请检查来源或稍后重试"
                self.store.update_instrument(identity, {"status": "error", "message": message})
                progress.update(status="failed", message=message)
                job["errors"].append({"instrument_id": identity, "symbol": instrument["symbol"], "provider": instrument["provider"], "message": message})
            job.update(added=sum(row["new"] for row in job["progress"]), updated=sum(row["updated"] for row in job["progress"]), total=sum(row["count"] for row in job["progress"]))
            self.store.save_job(job)
            await asyncio.sleep(.4)
        statuses = {row["status"] for row in job["progress"]}
        job.update(status="failed" if statuses <= {"failed", "skipped"} and "failed" in statuses else "partial" if statuses & {"failed", "partial"} else "completed", completed_at=now_iso())
        self.store.save_job(job)
