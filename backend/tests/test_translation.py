import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.store import Store
from app.translation import FIELDS, TranslationConfig, TranslationError, TranslationManager, source_hash


def make_item(store, identity="one", **changes):
    data = {"external_id": identity, "source": "x", "source_name": "X", "author": "writer", "title": "Market update", "content": "Rates increased today.", "summary": "A policy update.", "url": f"https://x.com/writer/status/{identity}"}
    data.update(changes)
    store.ingest(data, "following")
    return next(item for item in store.items()["items"] if item["external_id"] == identity)


def envelope(fields):
    translated = {field: "中文译文：" + value if value else "" for field, value in fields.items()}
    return json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(translated, ensure_ascii=False)}}]}, ensure_ascii=False).encode()


@pytest.mark.asyncio
async def test_complete_translation_cache_originals_and_model_version(monkeypatch, tmp_path):
    import app.translation as translation
    calls = []
    async def provider(url, **kwargs):
        calls.append(kwargs)
        return envelope(json.loads(kwargs["json_body"]["messages"][1]["content"]))
    monkeypatch.setattr(translation, "fetch_url", provider)
    store = Store(tmp_path / "data.sqlite3")
    original = make_item(store)
    manager = TranslationManager(store, TranslationConfig(api_key="LOCAL_TEST_ONLY"))
    result = await manager.translate(original["id"])
    assert all(result[field] == "中文译文：" + original[field] for field in FIELDS)
    assert result["source_hash"] == source_hash(original)
    assert result["language"] == "zh" and result["model"] == "deepseek-flash"
    item = store.get_item(original["id"])
    assert all(item[field] == original[field] for field in FIELDS)
    assert item["translation"] == result
    await manager.translate(original["id"])
    store.update_item(original["id"], {"bookmarked": True, "is_read": True})
    await manager.translate(original["id"])
    assert len(calls) == 1
    assert calls[0]["json_body"]["thinking"] == {"type": "disabled"}
    assert calls[0]["json_body"]["response_format"] == {"type": "json_object"}
    revised_model = TranslationManager(store, TranslationConfig(api_key="LOCAL_TEST_ONLY", model="deepseek-flash-next"))
    assert store.get_item(original["id"])["translation"] is None
    await revised_model.translate(original["id"])
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_original_and_summary_changes_invalidate_cache_and_chinese_search(monkeypatch, tmp_path):
    import app.translation as translation
    async def provider(url, **kwargs):
        return envelope(json.loads(kwargs["json_body"]["messages"][1]["content"]))
    monkeypatch.setattr(translation, "fetch_url", provider)
    store = Store(tmp_path / "data.sqlite3")
    item = make_item(store)
    manager = TranslationManager(store, TranslationConfig(api_key="TEST_ONLY"))
    await manager.translate(item["id"])
    assert store.items(q="中文译文")["total"] == 1
    store.update_item(item["id"], {"summary": "An edited summary."})
    assert store.get_item(item["id"])["translation"] is None
    assert store.items(q="中文译文")["total"] == 0
    await manager.translate(item["id"])
    assert store.items(q="中文译文")["total"] == 1
    # An edited provider post may become shorter; do not keep its old original body.
    make_item(store, content="Short correction.")
    assert store.get_item(item["id"])["content"] == "Short correction."
    assert store.get_item(item["id"])["translation"] is None


@pytest.mark.asyncio
async def test_chinese_only_skips_provider_but_mixed_language_does_not(monkeypatch, tmp_path):
    import app.translation as translation
    calls = []
    async def provider(url, **kwargs):
        calls.append(url)
        return envelope(json.loads(kwargs["json_body"]["messages"][1]["content"]))
    monkeypatch.setattr(translation, "fetch_url", provider)
    store = Store(tmp_path / "data.sqlite3")
    chinese = make_item(store, title="市场动态", content="利率上调。", summary="政策更新。")
    mixed = make_item(store, "two", title="市场 Bitcoin 动态", content="利率上调。", summary="政策更新。")
    manager = TranslationManager(store, TranslationConfig(api_key="TEST_ONLY"))
    result = await manager.translate(chinese["id"])
    assert all(result[field] == chinese[field] for field in FIELDS)
    assert not calls
    await manager.translate(mixed["id"])
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_long_content_is_fully_chunked_not_silently_truncated(monkeypatch, tmp_path):
    import app.translation as translation
    sent = []
    async def provider(url, **kwargs):
        fields = json.loads(kwargs["json_body"]["messages"][1]["content"])
        sent.append(fields)
        return envelope(fields)
    monkeypatch.setattr(translation, "fetch_url", provider)
    store = Store(tmp_path / "data.sqlite3")
    body = "Long original paragraph. " * 800 + "END_MARKER"
    item = make_item(store, content=body)
    manager = TranslationManager(store, TranslationConfig(api_key="TEST_ONLY"))
    result = await manager.translate(item["id"])
    assert "".join(fields["content"] for fields in sent) == body
    assert "END_MARKER" in result["content"]
    assert all(sum(len(value) for value in fields.values()) <= 6000 for fields in sent)
    assert result["title"] and result["summary"]


@pytest.mark.asyncio
async def test_shared_jobs_deduplicate_calls_and_global_concurrency_is_two(monkeypatch, tmp_path):
    import app.translation as translation
    active = peak = 0
    calls = []
    async def provider(url, **kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        fields = json.loads(kwargs["json_body"]["messages"][1]["content"])
        calls.append(fields)
        await asyncio.sleep(0.025)
        active -= 1
        return envelope(fields)
    monkeypatch.setattr(translation, "fetch_url", provider)
    store = Store(tmp_path / "data.sqlite3")
    ids = [make_item(store, str(number))["id"] for number in range(6)]
    manager = TranslationManager(store, TranslationConfig(api_key="TEST_ONLY"))
    first, second = manager.new_job(ids), manager.new_job(ids)
    await asyncio.gather(manager.run_job(first, ids), manager.run_job(second, ids))
    assert len(calls) == 6 and peak == 2
    assert first["completed"] == second["completed"] == 6
    assert not manager.inflight


@pytest.mark.asyncio
async def test_schema_failure_provider_error_and_missing_items_are_safe(monkeypatch, tmp_path):
    import app.translation as translation
    async def provider(url, **kwargs):
        request = httpx.Request("POST", url, headers={"Authorization": "Bearer SECRET_NEVER_OUTPUT"})
        response = httpx.Response(401, request=request, content=b"provider SECRET_NEVER_OUTPUT")
        raise httpx.HTTPStatusError("raw SECRET_NEVER_OUTPUT", request=request, response=response)
    monkeypatch.setattr(translation, "fetch_url", provider)
    store = Store(tmp_path / "data.sqlite3")
    item = make_item(store)
    manager = TranslationManager(store, TranslationConfig(api_key="SECRET_NEVER_OUTPUT"))
    job = manager.new_job([item["id"], "missing"])
    await manager.run_job(job, [item["id"], "missing"])
    assert job["status"] == "completed" and job["failed"] == 2 and job["completed"] == 0
    assert "SECRET_NEVER_OUTPUT" not in json.dumps(job)
    assert store.get_item(item["id"])["translation"] is None
    async def malformed(url, **kwargs):
        return json.dumps({"choices": [{"message": {"content": '{"title":"中文","content":"中文"}'}}]}).encode()
    monkeypatch.setattr(translation, "fetch_url", malformed)
    with pytest.raises(TranslationError):
        await manager.translate(item["id"])
    assert store.get_item(item["id"])["translation"] is None


@pytest.mark.asyncio
async def test_source_change_during_request_cannot_write_stale_translation(monkeypatch, tmp_path):
    import app.translation as translation
    store = Store(tmp_path / "data.sqlite3")
    item = make_item(store)
    async def provider(url, **kwargs):
        store.update_item(item["id"], {"summary": "New original summary"})
        return envelope(json.loads(kwargs["json_body"]["messages"][1]["content"]))
    monkeypatch.setattr(translation, "fetch_url", provider)
    manager = TranslationManager(store, TranslationConfig(api_key="TEST_ONLY"))
    with pytest.raises(TranslationError, match="source changed"):
        await manager.translate(item["id"])
    assert store.get_item(item["id"])["translation"] is None


def test_environment_flash_config_and_status_never_exposes_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "SECRET_NOT_PRINTED")
    monkeypatch.setenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_FLASH_MODEL", raising=False)
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-pro")
    config = TranslationConfig.from_environment()
    assert config.model == "deepseek-flash"
    assert config.endpoint == "https://api.deepseek.com/v1/chat/completions"
    assert config.status()["configured"]
    assert "SECRET_NOT_PRINTED" not in json.dumps(config.status())
    assert "SECRET_NOT_PRINTED" not in repr(config)
    monkeypatch.setenv("DEEPSEEK_FLASH_MODEL", "deepseek-pro")
    assert TranslationConfig.from_environment().status()["configured"]
    monkeypatch.setenv("DEEPSEEK_FLASH_MODEL", "invalid model name")
    assert not TranslationConfig.from_environment().status()["configured"]


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_reason", ["length", "content_filter", "tool_calls", None])
async def test_noncompleted_provider_output_is_never_cached(monkeypatch, tmp_path, finish_reason):
    import app.translation as translation
    async def provider(url, **kwargs):
        response = json.loads(envelope(json.loads(kwargs["json_body"]["messages"][1]["content"])))
        response["choices"][0]["finish_reason"] = finish_reason
        return json.dumps(response).encode()
    monkeypatch.setattr(translation, "fetch_url", provider)
    store = Store(tmp_path / "data.sqlite3")
    item = make_item(store)
    manager = TranslationManager(store, TranslationConfig(api_key="TEST_ONLY"))
    with pytest.raises(TranslationError):
        await manager.translate(item["id"])
    assert store.get_item(item["id"])["translation"] is None


@pytest.mark.asyncio
async def test_hard_size_limit_returns_error_without_partial_request_or_cache(monkeypatch, tmp_path):
    import app.translation as translation
    calls = []
    async def provider(url, **kwargs):
        calls.append(url)
        return envelope(json.loads(kwargs["json_body"]["messages"][1]["content"]))
    monkeypatch.setattr(translation, "fetch_url", provider)
    store = Store(tmp_path / "data.sqlite3")
    item = make_item(store, content="A" * 180001)
    manager = TranslationManager(store, TranslationConfig(api_key="TEST_ONLY"))
    with pytest.raises(TranslationError, match="truncated"):
        await manager.translate(item["id"])
    assert not calls and store.get_item(item["id"])["translation"] is None


def test_api_completed_job_returns_only_its_items_with_cache(monkeypatch, tmp_path):
    import app.translation as translation
    async def provider(url, **kwargs):
        return envelope(json.loads(kwargs["json_body"]["messages"][1]["content"]))
    monkeypatch.setattr(translation, "fetch_url", provider)
    with TestClient(create_app(tmp_path)) as client:
        service = client.app.state.service
        item = make_item(service.store)
        make_item(service.store, "other")
        service.translation = TranslationManager(service.store, TranslationConfig(api_key="SECRET_TEST_ONLY"))
        status = client.get("/api/translation/status").json()
        assert status["configured"] and "SECRET_TEST_ONLY" not in str(status)
        response = client.post("/api/translate", json={"ids": [item["id"], "missing"], "target_language": "zh"})
        assert response.status_code == 202
        job = response.json()
        for _ in range(50):
            completed = client.get("/api/translation/jobs/" + job["id"]).json()
            if completed["status"] != "running":
                break
        assert completed["completed"] == 1 and completed["failed"] == 1
        assert len(completed["items"]) == 1 and completed["items"][0]["id"] == item["id"]
        assert all(completed["items"][0]["translation"][field] for field in FIELDS)
        assert client.post("/api/translate", json={"ids": ["bad"] * 61}).status_code == 422
        assert client.post("/api/translate", json={"ids": ["bad"], "target_language": "en"}).status_code == 422
