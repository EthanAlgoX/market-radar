from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Query, Request

from .models import RefreshRequest, WatchlistRequest
from .service import MarketService


def create_market_router(getter: Callable[[Request], MarketService]) -> APIRouter:
    router = APIRouter(prefix="/api/market", tags=["market"])

    @router.get("/overview")
    async def overview(request: Request):
        return getter(request).overview()

    @router.post("/watchlist", status_code=201)
    async def add(request: Request, payload: WatchlistRequest):
        try:
            return getter(request).add_watchlist(payload.market, payload.symbol)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.delete("/watchlist/{identity}")
    async def delete(request: Request, identity: str):
        if not getter(request).delete_watchlist(identity):
            raise HTTPException(404, "自选标的不存在")
        return {"deleted": True, "id": identity}

    @router.post("/refresh", status_code=202)
    async def refresh(request: Request, payload: RefreshRequest):
        try:
            return getter(request).new_job(payload.ids)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/jobs/{identity}")
    async def job(request: Request, identity: str):
        result = getter(request).get_job(identity)
        if result is None:
            raise HTTPException(404, "行情任务不存在")
        return result

    @router.get("/instruments/{identity}")
    async def snapshot(request: Request, identity: str, limit: int = Query(180, ge=1, le=180)):
        result = getter(request).snapshot(identity, limit)
        if result is None:
            raise HTTPException(404, "自选标的不存在")
        return result

    return router
