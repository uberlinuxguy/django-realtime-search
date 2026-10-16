import datetime
import json
import re

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase

from realtime_search.admin import SearchFiltersMixin
from realtime_search.filters import normalize_search_filters, parse_search_term
from tests.testapp.models import Author, Book


class ParseSearchTermTests(SimpleTestCase):
    keys = {"author", "year", "in_print"}

    def parse(self, term):
        tokens, remaining = parse_search_term(term, self.keys)
        return [tuple(t) for t in tokens], remaining

    def test_plain_text_untouched(self):
        self.assertEqual(self.parse('dark "left hand"'), ([], 'dark "left hand"'))

    def test_filters_extracted(self):
        self.assertEqual(
            self.parse("author:butler dark year:>=1990"),
            ([("author", None, "butler", False), ("year", ">=", "1990", False)], "dark"),
        )

    def test_quoted_value_and_operators(self):
        self.assertEqual(
            self.parse('author:="octavia butler" -in_print:yes author:^oct'),
            (
                [
                    ("author", "=", "octavia butler", False),
                    ("in_print", None, "yes", True),
                    ("author", "^", "oct", False),
                ],
                "",
            ),
        )

    def test_keys_case_insensitive(self):
        self.assertEqual(self.parse("Author:x")[0], [("author", None, "x", False)])

    def test_unknown_key_is_search_text(self):
        self.assertEqual(self.parse("Re:Joyce foo:bar"), ([], "Re:Joyce foo:bar"))

    def test_empty_value_ignored(self):
        self.assertEqual(self.parse("author: year:> dark"), ([], "dark"))


class NormalizeTests(SimpleTestCase):
    def test_list_form(self):
        specs = normalize_search_filters(Book, ["in_print", "author__name"])
        self.assertEqual(set(specs), {"in_print", "author__name"})

    def test_explicit_lookup_and_transform(self):
        specs = normalize_search_filters(
            Book, {"exact_author": "author__name__iexact", "year": "published__year"}
        )
        self.assertEqual(specs["exact_author"].lookup, "iexact")
        self.assertTrue(specs["year"].is_transform)

    def test_bad_paths(self):
        for path in ["nope", "author__nope", "title__nope", "in_print__name"]:
            with self.subTest(path=path), self.assertRaises(ImproperlyConfigured):
                normalize_search_filters(Book, {"x": path})

    def test_system_checks(self):
        class BadAdmin(SearchFiltersMixin, admin.ModelAdmin):
            search_fields = ["title"]
            search_filters = {"x": "nope"}

        class NoSearchFieldsAdmin(SearchFiltersMixin, admin.ModelAdmin):
            search_filters = ["title"]

        site = admin.AdminSite()
        ids = [e.id for e in BadAdmin(Book, site).check()]
        self.assertIn("realtime_search.E001", ids)
        ids = [e.id for e in NoSearchFieldsAdmin(Book, site).check()]
        self.assertIn("realtime_search.E002", ids)


class SearchFiltersAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser("admin", "a@example.com", "pw")
        le_guin = Author.objects.create(name="Ursula K. Le Guin")
        butler = Author.objects.create(name="Octavia Butler")
        books = [
            ("The Left Hand of Darkness", le_guin, 1969, True, "hc"),
            ("The Dispossessed", le_guin, 1974, False, "pb"),
            ("Parable of the Sower", butler, 1993, True, "eb"),
            ("Parable of the Talents", butler, 1998, False, "hc"),
        ]
        for title, author, year, in_print, fmt in books:
            Book.objects.create(
                title=title, author=author, published=datetime.date(year, 6, 1),
                in_print=in_print, format=fmt,
            )

    def setUp(self):
        self.client.force_login(self.user)

    def search(self, q):
        response = self.client.get("/admin/testapp/book/", {"q": q})
        self.assertEqual(response.status_code, 200)
        return sorted(str(b) for b in response.context["cl"].result_list)

    def test_text_contains_across_relation(self):
        self.assertEqual(self.search("author:butler"), ["Parable of the Sower", "Parable of the Talents"])

    def test_text_operators(self):
        self.assertEqual(len(self.search('author:="ursula k. le guin"')), 2)
        self.assertEqual(self.search("author:=butler"), [])
        self.assertEqual(len(self.search("author:^oct")), 2)
        self.assertEqual(self.search("author:^butler"), [])

    def test_boolean(self):
        self.assertEqual(self.search("in_print:no"), ["Parable of the Talents", "The Dispossessed"])
        self.assertEqual(self.search("in_print:YES"), self.search("in_print:true"))
        self.assertEqual(self.search("in_print:maybe"), [])

    def test_negation(self):
        self.assertEqual(self.search("-in_print:yes"), self.search("in_print:no"))
        self.assertEqual(self.search("-author:butler"), ["The Dispossessed", "The Left Hand of Darkness"])

    def test_date_and_year(self):
        self.assertEqual(self.search("published:1993"), ["Parable of the Sower"])
        self.assertEqual(self.search("published:>1990"), ["Parable of the Sower", "Parable of the Talents"])
        self.assertEqual(self.search("published:<=1974-06-01"), ["The Dispossessed", "The Left Hand of Darkness"])
        self.assertEqual(self.search("year:>=1974 year:<1998"), ["Parable of the Sower", "The Dispossessed"])

    def test_choices_by_value_label_or_prefix(self):
        self.assertEqual(self.search("format:eb"), ["Parable of the Sower"])
        self.assertEqual(self.search("format:e-book"), ["Parable of the Sower"])
        self.assertEqual(len(self.search("format:hard")), 2)
        self.assertEqual(self.search("format:=hard"), [])
        self.assertEqual(self.search("format:vinyl"), [])

    def test_combined_with_free_text(self):
        self.assertEqual(self.search("parable in_print:yes"), ["Parable of the Sower"])
        self.assertEqual(self.search('"left hand" author:guin'), ["The Left Hand of Darkness"])

    def test_invalid_values_return_nothing_not_errors(self):
        for q in ["year:abc", "published:1993-0", "published:^1993", "in_print:>1"]:
            with self.subTest(q=q):
                self.assertEqual(self.search(q), [])

    def test_unfinished_filter_ignored(self):
        self.assertEqual(len(self.search("author:")), 4)

    def test_unknown_key_searches_as_text(self):
        self.assertEqual(self.search("nope:x"), [])
        Book.objects.create(
            title="Re:Coded", author=Author.objects.first(), published=datetime.date(2000, 1, 1)
        )
        self.assertEqual(self.search("re:coded"), ["Re:Coded"])

    def test_hints_in_config(self):
        response = self.client.get("/admin/testapp/book/")
        config = json.loads(
            re.search(
                r'id="realtime-search-config" type="application/json">(.*?)</script>',
                response.content.decode(),
            ).group(1)
        )
        self.assertEqual(
            config["filters"],
            [
                {"key": "author", "example": "author:something"},
                {"key": "in_print", "example": "in_print:yes"},
                {"key": "published", "example": "published:>2000"},
                {"key": "year", "example": "year:"},
                {"key": "format", "example": "format:Hardcover"},
            ],
        )
