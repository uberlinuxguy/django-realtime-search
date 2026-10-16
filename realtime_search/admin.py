from django.core import checks
from django.core.exceptions import FieldError, ImproperlyConfigured, ValidationError

from realtime_search.filters import (
    InvalidFilterValue,
    normalize_search_filters,
    parse_search_term,
)


class SearchFiltersMixin:
    """
    Lets users type ``key:value`` filters into the admin search box, e.g.
    ``author:butler in_print:no year:>=1990 parable``.

        class BookAdmin(SearchFiltersMixin, admin.ModelAdmin):
            search_fields = ["title"]
            search_filters = {
                "author": "author__name",
                "in_print": "in_print",
                "year": "published__year",
            }

    Only the keys listed in ``search_filters`` are recognised; anything else
    is passed through to the normal ``search_fields`` search.
    """

    search_filters = None

    def get_search_filters(self, request=None):
        return normalize_search_filters(self.model, self.search_filters)

    def get_search_results(self, request, queryset, search_term):
        specs = self.get_search_filters(request)
        tokens, remaining = parse_search_term(search_term, specs)

        may_have_duplicates = False
        for token in tokens:
            spec = specs[token.key]
            try:
                q = spec.q(token.op, token.value)
                queryset = queryset.exclude(q) if token.negate else queryset.filter(q)
            except (InvalidFilterValue, ValidationError, ValueError, TypeError, FieldError):
                # A value that can't match (e.g. "year:abc" or a half-typed
                # date) means no results, rather than an error page.
                return queryset.none(), False
            may_have_duplicates = may_have_duplicates or spec.spawns_duplicates(self.opts)

        queryset, search_duplicates = super().get_search_results(request, queryset, remaining)
        return queryset, may_have_duplicates or search_duplicates

    def check(self, **kwargs):
        errors = super().check(**kwargs)
        try:
            self.get_search_filters()
        except ImproperlyConfigured as e:
            errors.append(checks.Error(str(e), obj=self.__class__, id="realtime_search.E001"))
        else:
            if self.search_filters and not self.search_fields:
                errors.append(
                    checks.Error(
                        "search_filters requires search_fields to be set, otherwise "
                        "the admin doesn't show a search box.",
                        obj=self.__class__,
                        id="realtime_search.E002",
                    )
                )
        return errors
