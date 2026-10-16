from django import template

from realtime_search.admin import SearchFiltersMixin
from realtime_search.conf import get_config

register = template.Library()

EXAMPLES = {
    "boolean": "{key}:yes",
    "date": "{key}:>2000",
    "text": "{key}:something",
}


def filter_hints(model_admin):
    if not isinstance(model_admin, SearchFiltersMixin):
        return []
    hints = []
    for spec in model_admin.get_search_filters().values():
        if spec.kind == "choice" and spec.field.flatchoices:
            example = "%s:%s" % (spec.key, spec.field.flatchoices[0][1])
        else:
            example = EXAMPLES.get(spec.kind, "{key}:").format(key=spec.key)
        hints.append({"key": spec.key, "example": example})
    return hints


@register.simple_tag
def realtime_search_config(cl):
    """
    Return the JS config for a ChangeList, or None when realtime search
    should not be active (disabled, or the changelist has no search box).
    """
    if cl is None or not getattr(cl, "search_fields", None):
        return None
    model_admin = getattr(cl, "model_admin", None)
    config = get_config(model_admin)
    if config is None:
        return None
    return {
        "debounceMs": int(config["DEBOUNCE_MS"]),
        "minChars": int(config["MIN_CHARS"]),
        "filters": filter_hints(model_admin),
    }
