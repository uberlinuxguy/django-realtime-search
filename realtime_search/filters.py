"""
Parsing and applying ``key:value`` filters typed into the admin search box.
"""
import re
from collections import namedtuple

from django.contrib.admin.utils import NotRelationField, get_fields_from_path
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.db import models
from django.db.models.constants import LOOKUP_SEP
from django.utils.text import smart_split, unescape_string_literal

try:
    from django.contrib.admin.utils import lookup_spawns_duplicates
except ImportError:  # Django < 4.0
    from django.contrib.admin.utils import lookup_needs_distinct as lookup_spawns_duplicates

TOKEN_RE = re.compile(
    r"^(?P<negate>-)?(?P<key>\w+):(?P<op>>=|<=|>|<|=|\^)?(?P<value>.*)$", re.S
)
YEAR_RE = re.compile(r"^\d{4}$")

COMPARISONS = {">": "gt", ">=": "gte", "<": "lt", "<=": "lte"}
TEXT_LOOKUPS = {None: "icontains", "=": "iexact", "^": "istartswith", **COMPARISONS}
EXACT_LOOKUPS = {None: "exact", "=": "exact", **COMPARISONS}

TRUE_VALUES = {"1", "y", "yes", "t", "true", "on"}
FALSE_VALUES = {"0", "n", "no", "f", "false", "off"}

FilterToken = namedtuple("FilterToken", "key op value negate")


class InvalidFilterValue(Exception):
    """The value can't be applied to the field (e.g. ``in_print:maybe``)."""


class SearchFilter:
    """One allowed ``key:`` in the search box, bound to a model field path."""

    def __init__(self, model, key, path):
        self.key = key
        parts = path.split(LOOKUP_SEP)
        try:
            self.field = get_fields_from_path(model, path)[-1]
            self.path, self.lookup = path, None
        except (FieldDoesNotExist, NotRelationField):
            # The last part may be an explicit lookup or transform, e.g.
            # "published__year" or "author__name__iexact".
            if len(parts) < 2:
                raise ImproperlyConfigured(
                    "search_filters: %r is not a field on %s." % (path, model.__name__)
                )
            self.path, self.lookup = LOOKUP_SEP.join(parts[:-1]), parts[-1]
            try:
                self.field = get_fields_from_path(model, self.path)[-1]
            except (FieldDoesNotExist, NotRelationField):
                raise ImproperlyConfigured(
                    "search_filters: %r is not a field on %s." % (path, model.__name__)
                )
            self.is_transform = self.field.get_transform(self.lookup) is not None
            if not self.is_transform and self.field.get_lookup(self.lookup) is None:
                raise ImproperlyConfigured(
                    "search_filters: %r is not a valid lookup on %s." % (path, model.__name__)
                )

    @property
    def kind(self):
        if self.lookup:
            return "lookup"
        if isinstance(self.field, models.BooleanField):
            return "boolean"
        if self.field.choices:
            return "choice"
        if isinstance(self.field, (models.CharField, models.TextField)):
            return "text"
        if isinstance(self.field, models.DateField):
            return "date"
        return "exact"

    def q(self, op, value):
        """Return a Q object for ``key:<op><value>``."""
        kind = self.kind

        if kind == "lookup":
            if op in (None, "="):
                return models.Q(**{self._join(self.lookup): value})
            if self.is_transform and op in COMPARISONS:
                return models.Q(**{self._join(self.lookup, COMPARISONS[op]): value})
            raise InvalidFilterValue

        if kind == "boolean":
            if op not in (None, "="):
                raise InvalidFilterValue
            lowered = value.lower()
            if lowered in TRUE_VALUES:
                return models.Q(**{self.path: True})
            if lowered in FALSE_VALUES:
                return models.Q(**{self.path: False})
            raise InvalidFilterValue

        if kind == "choice":
            if op not in (None, "="):
                raise InvalidFilterValue
            return models.Q(**{self._join("in"): self._match_choices(value, prefix=op is None)})

        if kind == "text":
            return models.Q(**{self._join(TEXT_LOOKUPS[op]): value})

        if op not in EXACT_LOOKUPS:
            raise InvalidFilterValue
        if kind == "date" and YEAR_RE.match(value):
            # "published:1993" / "published:>1990" mean the year.
            return models.Q(**{self._join("year", EXACT_LOOKUPS[op]): int(value)})
        return models.Q(**{self._join(EXACT_LOOKUPS[op]): value})

    def _join(self, *lookups):
        return LOOKUP_SEP.join((self.path,) + lookups)

    def _match_choices(self, value, prefix):
        # Match the stored value or the human label, case-insensitively.
        # Without an operator, a prefix of the label also matches, so results
        # narrow sensibly while the user is still typing.
        lowered = value.lower()
        choices = [(k, str(k).lower(), str(label).lower()) for k, label in self.field.flatchoices]
        exact = [k for k, key, label in choices if lowered in (key, label)]
        if exact or not prefix:
            matches = exact
        else:
            matches = [k for k, key, label in choices if label.startswith(lowered)]
        if not matches:
            raise InvalidFilterValue
        return matches

    def spawns_duplicates(self, opts):
        return lookup_spawns_duplicates(opts, self.path)


def normalize_search_filters(model, search_filters):
    """
    Turn ``ModelAdmin.search_filters`` (a dict of key -> field path, or a list
    of field paths) into ``{key: SearchFilter}``.
    """
    if not search_filters:
        return {}
    if isinstance(search_filters, dict):
        items = search_filters.items()
    else:
        items = ((path, path) for path in search_filters)
    result = {}
    for key, path in items:
        if not re.match(r"^\w+$", key):
            raise ImproperlyConfigured(
                "search_filters: key %r may only contain letters, digits and _." % key
            )
        result[key.lower()] = SearchFilter(model, key, path)
    return result


def parse_search_term(search_term, keys):
    """
    Split a search term into ``key:value`` filter tokens (for known keys) and
    the remaining free-text search, which is returned as a string.
    """
    filters, terms = [], []
    for bit in smart_split(search_term):
        match = TOKEN_RE.match(bit)
        if match and match.group("key").lower() in keys:
            value = match.group("value")
            if len(value) > 1 and value[0] in "\"'" and value[0] == value[-1]:
                value = unescape_string_literal(value)
            if value:  # "author:" with nothing yet is ignored while typing.
                filters.append(
                    FilterToken(
                        match.group("key").lower(),
                        match.group("op"),
                        value,
                        bool(match.group("negate")),
                    )
                )
        else:
            terms.append(bit)
    return filters, " ".join(terms)
