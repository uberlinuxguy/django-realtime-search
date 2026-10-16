from django.conf import settings

DEFAULTS = {
    # Turn realtime search on for every admin changelist that has search_fields.
    # Set to False to make it opt-in per ModelAdmin (``realtime_search = True``).
    "ENABLED": True,
    # Milliseconds to wait after the last keystroke before searching.
    "DEBOUNCE_MS": 300,
    # Minimum number of characters before a search fires. Clearing the box
    # always fires, so the full list comes back.
    "MIN_CHARS": 1,
}


def get_config(model_admin=None):
    """
    Return the effective config for a ModelAdmin, or None if realtime search
    is disabled for it.

    ``ModelAdmin.realtime_search`` may be:
      * unset / None - use the REALTIME_SEARCH setting
      * True / False - force on or off
      * a dict       - force on, overriding individual setting keys
    """
    config = dict(DEFAULTS)
    config.update(getattr(settings, "REALTIME_SEARCH", {}))

    override = getattr(model_admin, "realtime_search", None)
    if isinstance(override, dict):
        config.update(override)
        config["ENABLED"] = override.get("ENABLED", True)
    elif override is not None:
        config["ENABLED"] = bool(override)

    if not config["ENABLED"]:
        return None
    return config
