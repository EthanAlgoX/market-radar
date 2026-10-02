import asyncio
import json
import stat

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.store import Store
from app.translation import TranslationConfig, TranslationManager, source_hash
from test_translation import envelope, make_item


@pytest.fixture
def isolated_environment(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    for name in ("DEEPSEEK_BASE_URL", "DEEPSEEK_API_BASE", "DEEPSEEK_FLASH_MODEL"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_configuration_is_encrypted_redacted_hot_loaded_and_persistent(isolated_environment, tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        initial = client.get("/api/translation/config").json()
        assert initial["source"] == "none" and not initial["configured"]
        assert initial["error_code"] == "translation_not_configured"
        assert initial["base_url"] == "https://api.deepseek.com" and initial["model"] == "deepseek-flash"
        missing = client.patch("/api/translation/config", json={"base_url": "https://example.com/v1", "model": "vendor/model:version"})
        assert missing.status_code == 400 and missing.json()["detail"]["error_code"] == "translation_api_key_required"
        saved = client.patch("/api/translation/config", json={"base_url": "https://example.com/v1/", "model": "vendor/model:version", "api_key": "TOP_SECRET_CONFIG_TEST_ONLY"})
        assert saved.status_code == 200
        result = saved.json()
        assert result["configured"] and result["api_key_set"] and result["local_api_key_set"]
        assert result["source"] == "local" and not result["environment_available"]
        assert result["base_url"] == "https://example.com/v1" and result["model"] == "vendor/model:version"
        assert "TOP_SECRET_CONFIG_TEST_ONLY" not in saved.text
        assert "TOP_SECRET_CONFIG_TEST_ONLY" not in client.get("/api/translation/config").text
        assert "TOP_SECRET_CONFIG_TEST_ONLY" not in client.get("/api/translation/status").text
        assert "TOP_SECRET_CONFIG_TEST_ONLY" not in (tmp_path / "secrets.enc").read_text()
        assert "TOP_SECRET_CONFIG_TEST_ONLY" not in str(client.app.state.service.store.settings())
        assert stat.S_IMODE((tmp_path / "secrets.enc").stat().st_mode) == 0o600
        assert stat.S_IMODE((tmp_path / ".secrets.key").stat().st_mode) == 0o600
        assert client.app.state.service.translation.config.model == "vendor/model:version"
        retained = client.patch("/api/translation/config", json={"api_key": "", "model": "next-model"}).json()
        assert retained["configured"] and retained["model"] == "next-model"
        assert client.app.state.service.translation.config.api_key == "TOP_SECRET_CONFIG_TEST_ONLY"
    isolated_environment.setenv("DEEPSEEK_API_KEY", "ENVIRONMENT_TEST_ONLY")
    with TestClient(create_app(tmp_path)) as restarted:
        result = restarted.get("/api/translation/config").json()
        assert result["source"] == "local" and result["environment_available"]
        assert result["model"] == "next-model"
        assert restarted.app.state.service.translation.config.api_key == "TOP_SECRET_CONFIG_TEST_ONLY"
        cleared = restarted.delete("/api/translation/config").json()
        assert cleared["source"] == "environment" and cleared["configured"]
        assert cleared["api_key_set"] and not cleared["local_api_key_set"]
        assert cleared["model"] == "deepseek-flash"
        assert restarted.app.state.service.translation.config.api_key == "ENVIRONMENT_TEST_ONLY"
        assert restarted.app.state.service.secrets.get("translation_config") is None
        assert "ENVIRONMENT_TEST_ONLY" not in json.dumps(cleared)


def test_blank_key_cannot_transfer_environment_credentials_to_another_provider(isolated_environment, tmp_path):
    isolated_environment.setenv("DEEPSEEK_API_KEY", "ENV_TEST_ONLY")
    with TestClient(create_app(tmp_path)) as client:
        before = client.app.state.service.translation.config
        result = client.patch("/api/translation/config", json={"base_url": "https://another.example/v1", "model": "custom-model", "api_key": ""})
        assert result.status_code == 400 and "ENV_TEST_ONLY" not in result.text
        assert client.app.state.service.translation.config == before
        assert client.app.state.service.secrets.get("translation_config") is None
        retained = client.patch("/api/translation/config", json={"model": "deepseek-custom", "api_key": ""}).json()
        assert retained["source"] == "local" and retained["configured"]
        assert client.app.state.service.translation.config.api_key == "ENV_TEST_ONLY"


def test_local_provider_change_requires_explicit_key_and_preserves_configuration_on_rejection(isolated_environment, tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        client.patch("/api/translation/config", json={"base_url": "https://first.example/v1", "model": "same-model", "api_key": "FIRST_LOCAL_TEST_ONLY"})
        service = client.app.state.service
        before = service.translation.config
        saved_before = service.secrets.get("translation_config")
        normalized = client.patch("/api/translation/config", json={"base_url": "https://first.example/v1/", "api_key": ""})
        assert normalized.status_code == 200 and normalized.json()["configured"]
        assert service.translation.config == before
        for changes in ({"base_url": "https://second.example/v1"}, {"base_url": "https://second.example/v1", "api_key": ""}):
            response = client.patch("/api/translation/config", json=changes)
            assert response.status_code == 400
            assert response.json()["detail"]["error_code"] == "translation_api_key_required"
            assert "FIRST_LOCAL_TEST_ONLY" not in response.text
            assert service.translation.config == before
            assert service.secrets.get("translation_config") == saved_before
        updated = client.patch("/api/translation/config", json={"base_url": "https://second.example/v1", "api_key": "SECOND_LOCAL_TEST_ONLY"})
        assert updated.status_code == 200 and updated.json()["configured"]
        assert service.translation.config.base_url == "https://second.example/v1"
        assert service.translation.config.api_key == "SECOND_LOCAL_TEST_ONLY"
        assert "SECOND_LOCAL_TEST_ONLY" not in updated.text


@pytest.mark.parametrize("changes", [
    {"base_url": "ftp://example.com"}, {"base_url": "https://secret@example.com"},
    {"base_url": "https://@example.com"}, {"base_url": "https://example.com?key=SECRET_REJECTED"},
    {"base_url": "https://example.com/#SECRET_REJECTED"}, {"base_url": "https://example.com?"},
    {"base_url": "https://example.com:99999"}, {"base_url": "https://"},
    {"model": "bad model"}, {"model": "SECRET_REJECTED\ninvalid"},
    {"api_key": "SECRET_REJECTED\nheader"}, {"api_key": {"value": "SECRET_REJECTED"}},
    {"unexpected": "SECRET_REJECTED"},
])
def test_invalid_configuration_is_atomic_and_never_echoes_secrets(isolated_environment, tmp_path, changes):
    with TestClient(create_app(tmp_path)) as client:
        client.patch("/api/translation/config", json={"api_key": "OLD_TEST_ONLY"})
        before = client.app.state.service.translation.config
        response = client.patch("/api/translation/config", json={"api_key": "SECRET_REJECTED", **changes})
        assert response.status_code == 422
        assert "SECRET_REJECTED" not in response.text
        assert client.app.state.service.translation.config == before
        assert client.app.state.service.secrets.get("translation_config")["api_key"] == "OLD_TEST_ONLY"


def test_storage_failure_preserves_running_configuration_and_hides_exception(isolated_environment, tmp_path, monkeypatch):
    with TestClient(create_app(tmp_path)) as client:
        service = client.app.state.service
        before = service.translation.config
        def fail(*args, **kwargs):
            raise RuntimeError("RAW_SECRET_STORAGE_TEST_ONLY")
        monkeypatch.setattr(service.secrets, "set", fail)
        response = client.patch("/api/translation/config", json={"api_key": "REQUEST_SECRET_TEST_ONLY"})
        assert response.status_code == 500
        assert response.json()["detail"]["error_code"] == "translation_config_save_failed"
        assert "SECRET" not in response.text
        assert service.translation.config == before


def test_local_configuration_clear_without_environment_returns_setup_prompt(isolated_environment, tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        client.patch("/api/translation/config", json={"api_key": "LOCAL_TEST_ONLY"})
        result = client.delete("/api/translation/config").json()
        assert result["source"] == "none" and not result["configured"] and not result["api_key_set"]
        assert result["error_code"] == "translation_not_configured"
        assert client.get("/api/translation/status").json()["error_code"] == "translation_not_configured"


@pytest.mark.asyncio
async def test_inflight_chunks_and_new_requests_use_their_own_immutable_configuration(monkeypatch, tmp_path):
    import app.translation as translation
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    old = TranslationConfig(api_key="OLD_KEY_TEST_ONLY", base_url="https://old.example/v1", model="same-model")
    new = TranslationConfig(api_key="NEW_KEY_TEST_ONLY", base_url="https://new.example/v1", model="same-model")
    store = Store(tmp_path / "data.sqlite3")
    item = make_item(store, content="Long source content. " * 800)
    manager = TranslationManager(store, old)
    async def provider(url, **kwargs):
        fields = json.loads(kwargs["json_body"]["messages"][1]["content"])
        calls.append((url, kwargs["headers"]["Authorization"], kwargs["json_body"]["model"]))
        assert "thinking" not in kwargs["json_body"]
        if url.startswith("https://old.example") and not entered.is_set():
            entered.set()
            await release.wait()
        return envelope(fields)
    monkeypatch.setattr(translation, "fetch_url", provider)
    old_task = asyncio.create_task(manager.translate(item["id"]))
    await entered.wait()
    manager.update_config(new)
    new_task = asyncio.create_task(manager.translate(item["id"]))
    release.set()
    first, second = await asyncio.gather(old_task, new_task)
    assert first["model"] == second["model"] == "same-model"
    assert len([entry for entry in calls if entry[0].startswith("https://old.example")]) > 1
    assert len([entry for entry in calls if entry[0].startswith("https://new.example")]) > 1
    assert all(key == "Bearer OLD_KEY_TEST_ONLY" for url, key, _ in calls if url.startswith("https://old.example"))
    assert all(key == "Bearer NEW_KEY_TEST_ONLY" for url, key, _ in calls if url.startswith("https://new.example"))
    digest = source_hash(item)
    assert old.cache_key != new.cache_key
    assert store.get_translation(item["id"], digest, old.cache_key)
    assert store.get_translation(item["id"], digest, new.cache_key)
    count = len(calls)
    await manager.translate(item["id"])
    assert len(calls) == count


def test_api_translation_uses_saved_configuration_immediately(isolated_environment, tmp_path, monkeypatch):
    import app.translation as translation
    calls = []
    async def provider(url, **kwargs):
        calls.append((url, kwargs))
        return envelope(json.loads(kwargs["json_body"]["messages"][1]["content"]))
    monkeypatch.setattr(translation, "fetch_url", provider)
    with TestClient(create_app(tmp_path)) as client:
        item = make_item(client.app.state.service.store)
        client.patch("/api/translation/config", json={"api_key": "CUSTOM_TEST_ONLY", "base_url": "http://localhost:9000/v1", "model": "custom-model"})
        job = client.post("/api/translate", json={"ids": [item["id"]]}).json()
        for _ in range(60):
            result = client.get("/api/translation/jobs/" + job["id"]).json()
            if result["status"] != "running":
                break
        assert result["completed"] == 1 and not result["failed"]
        assert result["items"][0]["translation"]["model"] == "custom-model"
        assert "CUSTOM_TEST_ONLY" not in json.dumps(result)
        assert calls[0][0] == "http://localhost:9000/v1/chat/completions"
        assert calls[0][1]["headers"]["Authorization"] == "Bearer CUSTOM_TEST_ONLY"
        assert "thinking" not in calls[0][1]["json_body"]
        assert calls[0][1]["allow_loopback"]


def test_api_cache_scope_changes_when_same_model_moves_to_another_provider(isolated_environment, tmp_path, monkeypatch):
    import app.translation as translation
    calls = []
    async def provider(url, **kwargs):
        calls.append(url)
        return envelope(json.loads(kwargs["json_body"]["messages"][1]["content"]))
    monkeypatch.setattr(translation, "fetch_url", provider)
    with TestClient(create_app(tmp_path)) as client:
        item = make_item(client.app.state.service.store)
        first_config = client.patch("/api/translation/config", json={"api_key": "FIRST_TEST_ONLY", "base_url": "https://first.example/v1", "model": "same-model"}).json()
        def translate_item():
            job = client.post("/api/translate", json={"ids": [item["id"]]}).json()
            for _ in range(60):
                result = client.get("/api/translation/jobs/" + job["id"]).json()
                if result["status"] != "running":
                    break
            assert result["completed"] == 1 and not result["failed"]
            return result["items"][0]["translation"]
        first_value = translate_item()
        assert first_value["model"] == "same-model"
        assert first_value["cache_key"] == first_config["cache_key"]
        assert client.get("/api/translation/status").json()["cache_key"] == first_config["cache_key"]
        second_config = client.patch("/api/translation/config", json={"api_key": "SECOND_TEST_ONLY", "base_url": "https://second.example/v1", "model": "same-model"}).json()
        assert second_config["model"] == first_config["model"]
        assert second_config["cache_key"] != first_config["cache_key"]
        assert first_value["cache_key"] != second_config["cache_key"]
        assert client.get("/api/items").json()["items"][0]["translation"] is None
        second_value = translate_item()
        assert second_value["cache_key"] == second_config["cache_key"]
        assert client.get("/api/translation/config").json()["cache_key"] == second_config["cache_key"]
        assert calls == ["https://first.example/v1/chat/completions", "https://second.example/v1/chat/completions"]
        assert "TEST_ONLY" not in json.dumps([first_config, second_config, first_value, second_value])


@pytest.mark.asyncio
async def test_legacy_deepseek_cache_without_scope_remains_usable(monkeypatch, tmp_path):
    import app.translation as translation
    store = Store(tmp_path / "data.sqlite3")
    item = make_item(store)
    digest = source_hash(item)
    legacy = {"title": "旧译文", "content": "旧内容", "summary": "旧摘要", "language": "zh", "model": "deepseek-flash", "source_hash": digest, "translated_at": "2026-10-03T00:00:00+00:00"}
    assert store.save_translation(item["id"], digest, "deepseek-flash", legacy)
    async def unexpected_provider(*args, **kwargs):
        raise AssertionError("A legacy cached translation must not call its provider.")
    monkeypatch.setattr(translation, "fetch_url", unexpected_provider)
    manager = TranslationManager(store, TranslationConfig(api_key="TEST_ONLY"))
    assert manager.status()["cache_key"] == "deepseek-flash"
    assert await manager.translate(item["id"]) == legacy
    assert store.get_item(item["id"])["translation"] == legacy
