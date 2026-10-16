import datetime
import json
import re

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from tests.testapp.models import Author, Book

CONFIG_RE = re.compile(
    r'<script id="realtime-search-config" type="application/json">(.*?)</script>', re.S
)


class RealtimeSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser("admin", "a@example.com", "pw")
        le_guin = Author.objects.create(name="Ursula K. Le Guin")
        butler = Author.objects.create(name="Octavia Butler")
        Book.objects.create(title="The Dispossessed", author=le_guin, published=datetime.date(1974, 5, 1))
        Book.objects.create(title="Parable of the Sower", author=butler, published=datetime.date(1993, 1, 1))

    def setUp(self):
        self.client.force_login(self.user)

    def get_config(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        match = CONFIG_RE.search(response.content.decode())
        return response, (json.loads(match.group(1)) if match else None)

    def test_injected_on_changelist_with_search_fields(self):
        response, config = self.get_config("/admin/testapp/genre/")
        self.assertEqual(config, {"debounceMs": 300, "minChars": 1, "filters": []})
        self.assertContains(response, "realtime_search/realtime_search.js")
        self.assertContains(response, "realtime_search/realtime_search.css")

    def test_not_injected_without_search_fields(self):
        response, config = self.get_config("/admin/testapp/publisher/")
        self.assertIsNone(config)
        self.assertNotContains(response, "realtime_search.js")

    def test_model_admin_opt_out(self):
        _, config = self.get_config("/admin/testapp/tag/")
        self.assertIsNone(config)

    def test_model_admin_dict_overrides(self):
        _, config = self.get_config("/admin/testapp/author/")
        self.assertEqual(config, {"debounceMs": 100, "minChars": 2, "filters": []})

    @override_settings(REALTIME_SEARCH={"DEBOUNCE_MS": 500})
    def test_setting_overrides(self):
        _, config = self.get_config("/admin/testapp/author/")
        self.assertEqual(config["minChars"], 2)  # ModelAdmin dict wins
        _, config = self.get_config("/admin/testapp/genre/")
        self.assertEqual(config["debounceMs"], 500)

    @override_settings(REALTIME_SEARCH={"ENABLED": False})
    def test_globally_disabled(self):
        _, config = self.get_config("/admin/testapp/book/")
        self.assertIsNone(config)

    @override_settings(REALTIME_SEARCH={"ENABLED": False})
    def test_dict_override_opts_in_when_globally_disabled(self):
        _, config = self.get_config("/admin/testapp/author/")
        self.assertIsNotNone(config)

    def test_custom_change_list_template(self):
        response, config = self.get_config("/admin/testapp/genre/")
        self.assertContains(response, 'id="custom-tool"')
        self.assertIsNotNone(config)

    def test_changelist_markup_contract(self):
        """The JS relies on these elements in the admin's changelist HTML."""
        response = self.client.get("/admin/testapp/book/", {"q": "sower"})
        html = response.content.decode()
        for marker in ('id="changelist"', 'id="changelist-search"', 'id="searchbar"',
                       'id="changelist-form"', 'id="changelist-filter"', 'class="small quiet"'):
            self.assertIn(marker, html)
        # Date hierarchy: <div class="xfull"> before Django 4.1, <nav class="toplinks"> after.
        self.assertTrue('class="xfull"' in html or '<nav class="toplinks"' in html)
        self.assertIn("Parable of the Sower", html)
        self.assertNotIn("The Dispossessed", html)
