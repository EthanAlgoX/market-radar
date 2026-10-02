"""X adapter tests are offline; no real browser, login or X requests are used."""

import asyncio
import json
import sys
import tempfile
import time
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.connectors import x


class Secrets:
    def __init__(self):
        self.values = {}

    def get(self, name, default=None):
        return self.values.get(name, default)

    def set(self, name, value):
        self.values[name] = value

    def delete(self, name):
        self.values.pop(name, None)


class Checkpoints:
    def __init__(self):
        self.values = {}

    def get_checkpoint(self, key):
        return self.values.get(key)

    def save_checkpoint(self, key, value):
        self.values[key] = json.loads(json.dumps(value))


class Page(list):
    def __init__(self, items, following=None, cursor=None):
        super().__init__(items)
        self.next_cursor = cursor
        self.next = AsyncMock(return_value=following or Page.empty())

    @classmethod
    def empty(cls):
        result = list.__new__(cls)
        list.__init__(result, [])
        result.next_cursor = None
        result.next = AsyncMock(return_value=None)
        return result


def tweet(tweet_id, text="An ordinary day", author="writer", **overrides):
    values = {
        "id": str(tweet_id),
        "user": SimpleNamespace(id="100", screen_name=author),
        "created_at": "Fri Oct 02 08:30:00 +0000 2026",
        "full_text": text,
        "text": text,
        "favorite_count": 12,
        "reply_count": 3,
        "retweet_count": 4,
        "quote": None,
        "retweeted_tweet": None,
        "urls": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def client():
    return SimpleNamespace(
        set_cookies=Mock(),
        user=AsyncMock(return_value=SimpleNamespace(id="owner-id", screen_name="owner")),
        get_latest_timeline=AsyncMock(return_value=Page.empty()),
        get_timeline=AsyncMock(return_value=Page.empty()),
        search_tweet=AsyncMock(return_value=Page.empty()),
        get_user_by_screen_name=AsyncMock(return_value=SimpleNamespace(id="author-id", screen_name="writer")),
        get_user_tweets=AsyncMock(return_value=Page.empty()),
        get_user_following=AsyncMock(return_value=Page.empty()),
        http=SimpleNamespace(aclose=AsyncMock()),
    )


COOKIES = {"auth_token": "private-test-token", "ct0": "private-test-csrf"}


class CookieTests(unittest.TestCase):
    def test_accept_dict_and_browser_list_filter_other_domains(self):
        self.assertEqual(x.parse_cookies(json.dumps(COOKIES)), COOKIES)
        export = [
            {"name": key, "value": value, "domain": ".x.com"}
            for key, value in COOKIES.items()
        ] + [{"name": "unrelated", "value": "secret", "domain": ".example.org"}]
        self.assertEqual(x.parse_cookies(export), COOKIES)
        self.assertEqual(x.parse_cookies({"cookies": export}), COOKIES)

    def test_reject_missing_required_cookie_without_echoing_input(self):
        for value in ({"auth_token": "private-test-token"}, "private-test-token", [], {"auth_token": "\n", "ct0": "x"}):
            with self.assertRaises(ValueError) as error:
                x.parse_cookies(value)
            self.assertNotIn("private-test-token", str(error.exception))

    def test_repost_quote_keep_recommending_author_and_original_sources(self):
        original = tweet("11", "The original post", "original")
        quote = tweet("12", "A referenced discussion", "other")
        post = x.tweet_to_post(tweet("13", "RT", "followed", retweeted_tweet=original, quote=quote), "following")
        self.assertEqual(post["author"], "@followed")
        self.assertEqual(post["url"], "https://x.com/followed/status/13")
        self.assertIn("https://x.com/original/status/11", post["content"])
        self.assertIn("A referenced discussion", post["content"])
        self.assertEqual([ref["type"] for ref in post["references"]], ["repost", "quote"])
        self.assertEqual(post["metrics"], {"likes": 12, "comments": 3, "reposts": 4})
        self.assertEqual(post["published_at"], "2026-10-02T08:30:00+00:00")


class ConnectorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.secrets = Secrets()
        self.connector = x.XConnector(self.secrets, Path(self.temp.name))
        self.client = client()
        self.factory_patch = patch.object(x, "Client", return_value=self.client)
        self.factory = self.factory_patch.start()

    async def asyncTearDown(self):
        await self.connector.shutdown()
        self.factory_patch.stop()
        self.temp.cleanup()

    async def connect(self):
        result = await self.connector.save_cookies(json.dumps(COOKIES))
        self.assertEqual(result["state"], "connected")
        return result

    async def test_saved_cookies_are_confirmed_with_real_identity_call(self):
        result = await self.connect()
        self.client.user.assert_awaited_once()
        self.client.set_cookies.assert_called_once_with(COOKIES, clear_cookies=True)
        self.assertEqual(self.secrets.get("x.cookies"), COOKIES)
        self.assertEqual(result["username"], "owner")
        self.assertNotIn("private-test-token", json.dumps(result))
        self.assertEqual((await self.connector.status())["state"], "connected")

    async def test_restored_cookie_configuration_is_verified_on_first_status(self):
        self.secrets.set("x.cookies", COOKIES)
        self.secrets.set("x.account", {"username": "stale-user", "user_id": "stale"})
        result = await self.connector.status()
        self.client.user.assert_awaited_once()
        self.assertEqual(result["state"], "connected")
        self.assertEqual(result["username"], "owner")

    async def test_failed_validation_is_saved_but_never_marked_connected(self):
        Unauthorized = type("Unauthorized", (Exception,), {})
        self.client.user.side_effect = Unauthorized("private-test-token must not escape")
        result = await self.connector.save_cookies(json.dumps(COOKIES))
        self.assertEqual(result["state"], "error")
        self.assertTrue(result["configured"])
        self.assertIsNone(result["username"])
        self.assertNotIn("private-test-token", result["message"])
        self.assertIsNone(self.secrets.get("x.account"))
        self.client.http.aclose.assert_awaited_once()
        await self.connector.status()
        self.client.user.assert_awaited_once()  # Status polling does not hammer X.

    async def test_validation_timeout_is_explicit(self):
        async def never_returns():
            await asyncio.sleep(10)
        self.client.user.side_effect = never_returns
        self.connector.REQUEST_TIMEOUT = 0.01
        result = await self.connector.save_cookies(json.dumps(COOKIES))
        self.assertEqual(result["state"], "error")
        self.assertIn("超时", result["message"])
        self.assertTrue(result["configured"])

    async def test_following_keeps_posts_without_keyword(self):
        await self.connect()
        self.client.get_latest_timeline.return_value = Page([tweet("101", "My afternoon walk")])
        posts, errors = await self.connector.collect("following", query="cryptocurrency")
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["content"], "My afternoon walk")
        self.assertEqual(posts[0]["channels"], ["following"])
        self.client.get_latest_timeline.assert_awaited_once()
        self.client.search_tweet.assert_not_called()

    async def test_posts_use_identity_verified_during_collection_after_status_failure(self):
        self.secrets.set("x.cookies", COOKIES)
        Unauthorized = type("Unauthorized", (Exception,), {})
        self.client.user.side_effect = [
            Unauthorized("private-test-token"),
            SimpleNamespace(id="fresh-id", screen_name="fresh_owner"),
        ]
        stale = await self.connector.status()
        self.assertEqual(stale["state"], "error")
        self.assertIsNone(stale["username"])
        self.client.get_latest_timeline.return_value = Page([tweet("fresh-post", "Ordinary news")])
        posts, warnings = await self.connector.collect("following", query="crypto")
        self.assertFalse(warnings)
        self.assertEqual(posts[0]["account_id"], "fresh_owner")
        self.assertEqual(posts[0]["content"], "Ordinary news")
        self.assertEqual(self.client.user.await_count, 2)

    async def test_recommended_uses_personal_for_you_api(self):
        await self.connect()
        self.client.get_timeline.return_value = Page([tweet("102", "Recommended unrelated post")])
        posts, errors = await self.connector.collect("recommended", query="crypto")
        self.assertEqual(posts[0]["channels"], ["recommended"])
        self.client.get_timeline.assert_awaited_once()
        self.client.get_latest_timeline.assert_not_called()

    async def test_search_paginates_and_deduplicates(self):
        await self.connect()
        third = Page([tweet("203", "crypto three")])
        second = Page([tweet("201", "duplicate"), tweet("202", "crypto two")], third, "second")
        first = Page([tweet("201", "crypto one")], second, "first")
        self.client.search_tweet.return_value = first
        posts, errors = await self.connector.collect("search", query="crypto", limit=3)
        self.assertEqual([post["external_id"] for post in posts], ["201", "202", "203"])
        self.client.search_tweet.assert_awaited_once_with("crypto", "Latest", count=3)
        first.next.assert_awaited_once()
        second.next.assert_awaited_once()
        third.next.assert_not_called()

    async def test_pagination_is_bounded_and_does_not_stop_on_old_recommendation(self):
        await self.connect()
        extra = Page([tweet("303")])
        second = Page([tweet("302")], extra, "second")
        first = Page([tweet("301", created_at="Tue Oct 01 08:30:00 +0000 2024")], second, "first")
        self.client.get_timeline.return_value = first
        self.connector.MAX_PAGES = 2
        posts, errors = await self.connector.collect("recommended", limit=100)
        self.assertEqual([post["external_id"] for post in posts], ["301", "302"])
        first.next.assert_awaited_once()
        second.next.assert_not_called()
        self.assertTrue(any(warning["code"] == "truncated" for warning in errors))
        self.assertTrue((await self.connector.status())["truncated"])

    async def test_repeated_cursor_cannot_create_infinite_pagination(self):
        await self.connect()
        second = Page([tweet("312")], Page([tweet("313")]), "repeated")
        first = Page([tweet("311")], second, "repeated")
        self.client.get_timeline.return_value = first
        posts, errors = await self.connector.collect("recommended", limit=100)
        self.assertEqual([post["external_id"] for post in posts], ["311", "312"])
        second.next.assert_not_called()

    async def test_explicit_authors_are_collected_without_keyword_filter(self):
        await self.connect()
        self.client.get_latest_timeline.return_value = Page([tweet("400", "A followed person's repost")])
        self.client.get_user_tweets.return_value = Page([tweet("401", "Unrelated author post")])
        posts, errors = await self.connector.collect("following", "crypto", authors=["@writer"], limit=2)
        self.assertEqual([post["content"] for post in posts], ["A followed person's repost", "Unrelated author post"])
        self.client.get_user_by_screen_name.assert_awaited_once_with("writer")
        self.client.get_user_tweets.assert_awaited_once_with("author-id", "Tweets", count=1)
        self.client.get_latest_timeline.assert_awaited_once_with(count=1)
        self.client.search_tweet.assert_not_called()

    async def test_following_and_authors_share_total_budget_and_deduplicate(self):
        await self.connect()
        self.client.get_latest_timeline.return_value = Page([tweet("410"), tweet("411"), tweet("412")])
        self.client.get_user_tweets.return_value = Page([tweet("410"), tweet("413"), tweet("414")])
        posts, errors = await self.connector.collect("following", authors=["writer"], limit=5)
        self.assertEqual([post["external_id"] for post in posts], ["410", "411", "412", "413", "414"])
        self.assertLessEqual(len(posts), 5)
        self.client.get_latest_timeline.assert_awaited_once_with(count=3)
        self.client.get_user_tweets.assert_awaited_once_with("author-id", "Tweets", count=2)

    async def test_author_failure_does_not_silently_report_complete_following(self):
        await self.connect()
        self.client.get_latest_timeline.return_value = Page([tweet("420")])
        TooManyRequests = type("TooManyRequests", (Exception,), {})
        self.client.get_user_tweets.side_effect = TooManyRequests("private-test-token")
        posts, errors = await self.connector.collect("following", authors=["writer"], limit=5)
        self.assertEqual([post["external_id"] for post in posts], ["420"])
        self.assertTrue(any(error["code"] == "partial" and "429" in error["message"] for error in errors))
        self.assertNotIn("private-test-token", json.dumps(errors))
        self.client.get_latest_timeline.assert_awaited_once()

    async def test_failed_author_preserves_following_and_later_successful_author(self):
        await self.connect()
        self.client.get_latest_timeline.return_value = Page([tweet("421")])
        self.client.get_user_by_screen_name.side_effect = lambda handle: SimpleNamespace(id=handle)
        self.client.get_user_tweets.side_effect = [RuntimeError("Cookie private-test-token"), Page([tweet("422")])]
        posts, errors = await self.connector.collect("following", authors=["bad", "good"], limit=5)
        self.assertEqual([post["external_id"] for post in posts], ["421", "422"])
        self.assertTrue(any("@bad" in error["message"] and error["code"] == "partial" for error in errors))
        self.assertNotIn("private-test-token", json.dumps(errors))
        snapshot = await self.connector.status()
        self.assertEqual(snapshot["state"], "connected")
        self.assertIsNotNone(snapshot["last_success"])
        self.assertIsNotNone(snapshot["last_error"])

    async def test_author_authentication_error_is_fatal_and_discards_client(self):
        await self.connect()
        self.client.get_latest_timeline.return_value = Page([tweet("423")])
        Unauthorized = type("Unauthorized", (Exception,), {})
        self.client.get_user_tweets.side_effect = Unauthorized("Cookie private-test-token")
        with self.assertRaises(x.XAuthenticationError) as error:
            await self.connector.collect("following", authors=["writer"], limit=5)
        self.assertNotIn("private-test-token", str(error.exception))
        self.assertIsNone(self.connector._client)
        self.assertEqual(self.connector._state, "error")

    async def test_author_task_cancellation_is_never_downgraded_to_partial(self):
        await self.connect()
        self.client.get_user_tweets.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.connector.collect("following", authors=["writer"], limit=5)

    async def test_disconnect_during_author_lookup_cannot_return_old_results(self):
        await self.connect()
        async def disconnecting_lookup(handle):
            await self.connector.disconnect()
            return SimpleNamespace(id="old-session-author")
        self.client.get_user_by_screen_name.side_effect = disconnecting_lookup
        with self.assertRaises(x.XCancelledError):
            await self.connector.collect("following", authors=["writer"], limit=5)
        self.client.get_user_tweets.assert_not_awaited()
        self.assertEqual(self.connector._state, "disconnected")

    async def test_author_rotation_survives_restart_and_does_not_starve_after_fifty(self):
        await self.connect()
        checkpoints = Checkpoints()
        self.connector.store = checkpoints
        self.client.get_latest_timeline.return_value = Page([tweet("430"), tweet("431"), tweet("432")])
        self.client.get_user_by_screen_name.side_effect = lambda handle: SimpleNamespace(id=handle)
        self.client.get_user_tweets.side_effect = lambda author_id, *args, **kwargs: Page([tweet("author-" + author_id)])
        handles = ["writer" + str(index) for index in range(60)]
        visited = []
        for _ in range(26):
            await self.connector.collect("following", authors=handles, limit=5)
        visited = [call.args[0] for call in self.client.get_user_by_screen_name.await_args_list]
        self.assertEqual(visited, handles[:52])
        restored = x.XConnector(self.secrets, Path(self.temp.name), store=checkpoints)
        try:
            await restored.collect("following", authors=handles, limit=5)
            self.assertEqual(self.client.get_user_by_screen_name.await_args_list[-2].args[0], "writer52")
            self.assertEqual(checkpoints.get_checkpoint("x.capture")["author_offset"], 54)
            self.assertNotIn("high_water", checkpoints.get_checkpoint("x.capture"))
        finally:
            await restored.shutdown()

    async def test_author_id_cache_avoids_repeated_lookups_and_expires(self):
        await self.connect()
        self.client.get_user_tweets.return_value = Page([tweet("440")])
        for _ in range(2):
            await self.connector.collect("following", authors=["writer"], limit=5)
        self.client.get_user_by_screen_name.assert_awaited_once_with("writer")
        self.connector._user_ids["writer"]["cached_at"] -= self.connector.USER_ID_CACHE_TTL + 1
        await self.connector.collect("following", authors=["writer"], limit=5)
        self.assertEqual(self.client.get_user_by_screen_name.await_count, 2)

    async def test_duplicates_do_not_consume_author_unique_post_budget(self):
        await self.connect()
        self.client.get_latest_timeline.return_value = Page([tweet("450"), tweet("451"), tweet("452")])
        second = Page([tweet("454")])
        first = Page([tweet("450"), tweet("453")], second, "more")
        self.client.get_user_tweets.return_value = first
        posts, errors = await self.connector.collect("following", authors=["writer"], limit=5)
        self.assertEqual([post["external_id"] for post in posts], ["450", "451", "452", "453", "454"])
        first.next.assert_awaited_once()
        self.assertFalse(errors)

    async def test_partial_pagination_keeps_completed_pages(self):
        await self.connect()
        first = Page([tweet("460")], cursor="more")
        first.next.side_effect = RuntimeError("Cookie private-test-token")
        self.client.get_timeline.return_value = first
        posts, errors = await self.connector.collect("recommended", limit=10)
        self.assertEqual([post["external_id"] for post in posts], ["460"])
        self.assertTrue(any(error["code"] == "partial" for error in errors))
        self.assertNotIn("private-test-token", json.dumps(errors))

    async def test_item_limit_marks_truncated_even_without_next_cursor(self):
        await self.connect()
        self.client.get_timeline.return_value = Page([tweet("470"), tweet("471"), tweet("472")])
        posts, errors = await self.connector.collect("recommended", limit=2)
        self.assertEqual(len(posts), 2)
        self.assertEqual(errors[0]["code"], "truncated")
        snapshot = await self.connector.status()
        self.assertTrue(snapshot["truncated"])
        self.assertIsNotNone(snapshot["last_verified_at"])

    async def test_rate_limit_cooldown_skips_requests_and_is_per_endpoint(self):
        await self.connect()
        TooManyRequests = type("TooManyRequests", (Exception,), {})
        limited = TooManyRequests("private-test-token")
        limited.response = SimpleNamespace(status_code=429, headers={"Retry-After": "120"})
        self.client.get_timeline.side_effect = limited
        with patch.object(x.time, "time", return_value=2_000_000_000):
            for _ in range(2):
                with self.assertRaises(x.XRateLimitError):
                    await self.connector.collect("recommended")
            self.client.get_timeline.assert_awaited_once()
            self.assertEqual(self.connector._cooldowns["home_timeline"], 2_000_000_120)
            posts, errors = await self.connector.collect("following")
            self.client.get_latest_timeline.assert_awaited_once()
        self.client.get_timeline.side_effect = None
        self.client.get_timeline.return_value = Page([tweet("480")])
        with patch.object(x.time, "time", return_value=2_000_000_121):
            posts, errors = await self.connector.collect("recommended")
        self.assertEqual(posts[0]["external_id"], "480")
        self.assertNotIn("home_timeline", self.connector._cooldowns)

    async def test_rate_limit_reset_is_bounded_persisted_and_default_is_sixty_seconds(self):
        await self.connect()
        checkpoints = Checkpoints()
        self.connector.store = checkpoints
        TooManyRequests = type("TooManyRequests", (Exception,), {})
        limited = TooManyRequests()
        limited.rate_limit_reset = 2_000_200_000
        self.client.get_timeline.side_effect = limited
        with patch.object(x.time, "time", return_value=2_000_000_000):
            with self.assertRaises(x.XRateLimitError):
                await self.connector.collect("recommended")
            self.assertEqual(self.connector._cooldowns["home_timeline"], 2_000_000_000 + self.connector.MAX_COOLDOWN)
            restored = x.XConnector(self.secrets, Path(self.temp.name), store=checkpoints)
            self.assertEqual(restored._cooldowns, self.connector._cooldowns)
            self.assertEqual(self.connector._cooldown_until(TooManyRequests()), 2_000_000_060)
        await restored.shutdown()

    async def test_cached_session_revalidates_only_after_interval(self):
        await self.connect()
        await self.connector.collect("following")
        await self.connector.status()
        self.client.user.assert_awaited_once()
        self.connector._verified_monotonic = time.monotonic() - self.connector.SESSION_VERIFY_INTERVAL - 1
        await self.connector.collect("following")
        self.assertEqual(self.client.user.await_count, 2)
        self.assertEqual(self.factory.call_count, 1)

    async def test_partial_author_rate_limit_does_not_repeat_same_endpoint_for_other_authors(self):
        await self.connect()
        TooManyRequests = type("TooManyRequests", (Exception,), {})
        self.client.get_user_tweets.side_effect = TooManyRequests("private-test-token")
        self.client.get_user_by_screen_name.side_effect = lambda handle: SimpleNamespace(id=handle)
        self.client.get_latest_timeline.return_value = Page([tweet("490")])
        posts, errors = await self.connector.collect("following", authors=["one", "two", "three"], limit=5)
        self.assertEqual(len(posts), 1)
        self.client.get_user_tweets.assert_awaited_once()
        self.client.get_user_by_screen_name.assert_awaited_once_with("one")
        self.assertEqual(len([error for error in errors if error["code"] == "partial"]), 3)

    async def test_duplicate_author_pages_have_separate_small_page_bound(self):
        await self.connect()
        self.client.get_latest_timeline.return_value = Page([tweet("500")])
        fourth = Page([tweet("501")])
        third = Page([tweet("500")], fourth, "third")
        second = Page([tweet("500")], third, "second")
        first = Page([tweet("500")], second, "first")
        self.client.get_user_tweets.return_value = first
        posts, errors = await self.connector.collect("following", authors=["writer"], limit=5)
        self.assertEqual([post["external_id"] for post in posts], ["500"])
        third.next.assert_not_awaited()
        self.assertTrue(any(error["code"] == "truncated" for error in errors))

    async def test_following_list_paginates_with_current_account_id(self):
        await self.connect()
        second = Page([SimpleNamespace(id="b", screen_name="bob")])
        first = Page([SimpleNamespace(id="a", screen_name="alice")], second, "next")
        self.client.get_user_following.return_value = first
        self.assertEqual(await self.connector.following_accounts(limit=2), ["alice", "bob"])
        self.client.get_user_following.assert_awaited_once_with("owner-id", count=2)
        first.next.assert_awaited_once()

    async def test_rate_limit_is_clear_without_leaking_upstream_text(self):
        await self.connect()
        TooManyRequests = type("TooManyRequests", (Exception,), {})
        self.client.get_timeline.side_effect = TooManyRequests("Cookie private-test-token")
        with self.assertRaises(x.XConnectorError) as error:
            await self.connector.collect("recommended")
        self.assertIn("429", str(error.exception))
        self.assertNotIn("private-test-token", str(error.exception))
        self.assertEqual((await self.connector.status())["state"], "error")

    async def test_missing_credentials_never_calls_x(self):
        with self.assertRaises(x.MissingCredentials):
            await self.connector.collect("following")
        self.factory.assert_not_called()

    async def test_disconnect_during_validation_cannot_restore_session(self):
        entered = asyncio.Event()
        release = asyncio.Event()
        async def identify():
            entered.set()
            await release.wait()
            return SimpleNamespace(id="owner-id", screen_name="owner")
        self.client.user.side_effect = identify
        saving = asyncio.create_task(self.connector.save_cookies(COOKIES))
        await entered.wait()
        await self.connector.disconnect()
        release.set()
        result = await saving
        self.assertEqual(result["state"], "disconnected")
        self.assertIsNone(self.secrets.get("x.cookies"))
        self.assertIsNone(self.secrets.get("x.account"))

    async def test_login_starts_in_background_and_duplicate_call_reuses_task(self):
        wait = asyncio.Event()
        async def fake_browser(generation):
            await wait.wait()
        with patch.object(self.connector, "_browser_login", side_effect=fake_browser) as browser:
            result = await self.connector.start_login()
            first_task = self.connector._login_task
            self.assertEqual(result["state"], "connecting")
            await self.connector.start_login()
            self.assertIs(self.connector._login_task, first_task)
            await asyncio.sleep(0)
            browser.assert_called_once()
            await self.connector.disconnect()
            self.assertTrue(first_task.cancelled())
            self.assertEqual((await self.connector.status())["state"], "disconnected")

    async def test_browser_login_uses_new_isolated_profile_and_closes_it(self):
        browser_page = SimpleNamespace(goto=AsyncMock())
        browser_context = SimpleNamespace(
            pages=[browser_page],
            cookies=AsyncMock(return_value=[
                {"name": name, "value": value, "domain": ".x.com"}
                for name, value in COOKIES.items()
            ]),
            close=AsyncMock(),
        )
        chromium = SimpleNamespace(launch_persistent_context=AsyncMock(return_value=browser_context))
        class Manager:
            async def __aenter__(self):
                return SimpleNamespace(chromium=chromium)
            async def __aexit__(self, *args):
                return False
        module = types.ModuleType("playwright.async_api")
        module.async_playwright = Mock(return_value=Manager())
        parent = types.ModuleType("playwright")
        with patch.dict(sys.modules, {"playwright": parent, "playwright.async_api": module}):
            await self.connector.start_login()
            await self.connector._login_task
        options = chromium.launch_persistent_context.call_args.kwargs
        self.assertEqual(options["channel"], "chrome")
        self.assertFalse(options["headless"])
        self.assertEqual(Path(options["user_data_dir"]).parent, Path(self.temp.name) / "x-browser")
        self.assertFalse(Path(options["user_data_dir"]).exists())
        browser_context.close.assert_awaited_once()
        self.client.user.assert_awaited_once()
        self.assertEqual((await self.connector.status())["state"], "connected")

    async def test_browser_login_timeout_closes_profile_and_falls_back_to_chromium(self):
        browser_context = SimpleNamespace(
            pages=[SimpleNamespace(goto=AsyncMock())],
            cookies=AsyncMock(return_value=[]), close=AsyncMock(),
        )
        chromium = SimpleNamespace(launch_persistent_context=AsyncMock(side_effect=[RuntimeError("Chrome absent"), browser_context]))
        class Manager:
            async def __aenter__(self):
                return SimpleNamespace(chromium=chromium)
            async def __aexit__(self, *args):
                return False
        module = types.ModuleType("playwright.async_api")
        module.async_playwright = Mock(return_value=Manager())
        self.connector.LOGIN_TIMEOUT = 0
        with patch.dict(sys.modules, {"playwright": types.ModuleType("playwright"), "playwright.async_api": module}):
            await self.connector.start_login()
            await self.connector._login_task
        self.assertEqual(chromium.launch_persistent_context.call_count, 2)
        self.assertNotIn("channel", chromium.launch_persistent_context.call_args.kwargs)
        browser_context.close.assert_awaited_once()
        profile = chromium.launch_persistent_context.call_args.kwargs["user_data_dir"]
        self.assertFalse(Path(profile).exists())
        self.assertEqual((await self.connector.status())["state"], "error")
        self.assertIn("超时", (await self.connector.status())["message"])
        self.assertIsNone(self.secrets.get("x.cookies"))


if __name__ == "__main__":
    unittest.main()
