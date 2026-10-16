"""
End-to-end tests of the JavaScript in a real browser.

Skipped unless Playwright is installed:
    pip install playwright && playwright install chromium
"""
import datetime
import os
import unittest

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from tests.testapp.models import Author, Book

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

# Playwright's sync API runs an event loop, which trips Django's async guard.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


@unittest.skipIf(sync_playwright is None, "playwright is not installed")
class BrowserTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        get_user_model().objects.create_superuser("admin", "a@example.com", "pw")
        le_guin = Author.objects.create(name="Ursula K. Le Guin")
        butler = Author.objects.create(name="Octavia Butler")
        for i in range(15):
            Book.objects.create(
                title="Filler volume %d" % i, author=le_guin, published=datetime.date(1970, 1, 1)
            )
        Book.objects.create(
            title="Parable of the Sower", author=butler, published=datetime.date(1993, 1, 1)
        )
        Book.objects.create(
            title="Parable of the Talents", author=butler, published=datetime.date(1998, 1, 1),
            in_print=False,
        )

        self.page = self.browser.new_page()
        self.page.goto(self.live_server_url + "/admin/login/")
        self.page.fill("#id_username", "admin")
        self.page.fill("#id_password", "pw")
        self.page.click("input[type=submit]")
        self.page.wait_for_url("**/admin/")

    def tearDown(self):
        self.page.close()

    def open_changelist(self, query=""):
        self.page.goto(self.live_server_url + "/admin/testapp/book/" + query)
        # Marker that only survives if the page is never reloaded.
        self.page.evaluate("window.__noReload = true")

    def type_and_wait(self, text):
        with self.page.expect_response(lambda r: "/admin/testapp/book/" in r.url):
            self.page.fill("#searchbar", text)
        self.page.wait_for_function(
            "!document.getElementById('changelist').classList.contains('realtime-search-loading')"
        )

    def titles(self):
        return self.page.locator("#result_list tbody th a").all_inner_texts()

    def assert_not_reloaded(self):
        self.assertTrue(self.page.evaluate("window.__noReload === true"))

    def test_filters_as_you_type(self):
        self.open_changelist()
        self.assertEqual(len(self.titles()), 10)  # list_per_page

        self.type_and_wait("parable")
        self.assertEqual(sorted(self.titles()), ["Parable of the Sower", "Parable of the Talents"])
        self.assertIn("2 results", self.page.inner_text("#changelist-search .small.quiet"))
        self.assertIn("q=parable", self.page.url)
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "searchbar")

        self.type_and_wait("parable of the so")
        self.assertEqual(self.titles(), ["Parable of the Sower"])
        self.assert_not_reloaded()

    def test_clearing_restores_full_list(self):
        self.open_changelist("?q=sower")
        self.assertEqual(self.titles(), ["Parable of the Sower"])
        self.page.evaluate("window.__noReload = true")

        with self.page.expect_response(lambda r: "/admin/testapp/book/" in r.url):
            self.page.press("#searchbar", "Escape")
        self.page.wait_for_function("document.querySelectorAll('#result_list tbody tr').length === 10")
        self.assertEqual(self.page.locator("#changelist-search .small.quiet").count(), 0)
        self.assertNotIn("q=", self.page.url)
        self.assert_not_reloaded()

    def test_preserves_filters_and_resets_page(self):
        self.open_changelist("?in_print__exact=1&p=1")
        self.type_and_wait("parable")
        self.assertEqual(self.titles(), ["Parable of the Sower"])
        self.assertIn("in_print__exact=1", self.page.url)
        self.assertNotIn("p=", self.page.url.split("?")[1].replace("in_print", ""))
        # Sidebar filter links now carry the search term.
        self.assertIn(
            "q=parable",
            self.page.get_attribute("#changelist-filter a[href*='in_print__exact=0']", "href"),
        )

    def test_actions_rebound_after_update(self):
        self.open_changelist()
        self.type_and_wait("parable")
        self.page.check("#action-toggle")
        self.assertIn("2 of 2 selected", self.page.inner_text(".action-counter"))

    def test_min_chars(self):
        self.page.goto(self.live_server_url + "/admin/testapp/author/")
        requests = []
        self.page.on("request", lambda r: requests.append(r.url) if "q=" in r.url else None)
        self.page.fill("#searchbar", "o")  # AuthorAdmin sets MIN_CHARS = 2
        self.page.wait_for_timeout(400)
        self.assertEqual(requests, [])
        with self.page.expect_response(lambda r: "q=oc" in r.url):
            self.page.fill("#searchbar", "oc")

    def test_typed_filters(self):
        self.open_changelist()
        self.type_and_wait("parable in_print:no")
        self.assertEqual(self.titles(), ["Parable of the Talents"])
        self.type_and_wait("author:butler year:<1995")
        self.assertEqual(self.titles(), ["Parable of the Sower"])
        self.assert_not_reloaded()

    def test_filter_hint_inserts_key(self):
        self.open_changelist()
        self.page.fill("#searchbar", "parable")
        self.page.click(".realtime-search-filters button:has-text('in_print:')")
        self.assertEqual(self.page.input_value("#searchbar"), "parable in_print:")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "searchbar")
        with self.page.expect_response(lambda r: "in_print" in r.url):
            self.page.keyboard.type("no")
        self.page.wait_for_function(
            "document.querySelectorAll('#result_list tbody tr').length === 1"
        )
        self.assertEqual(self.titles(), ["Parable of the Talents"])
