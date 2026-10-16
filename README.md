# django-realtime-search

Filters Django admin changelist pages as you type in the search box. You don't need to press Enter or wait for a page reload.

You don't change any of your existing admins. Every search fetches the normal changelist URL, so your `search_fields`, `get_search_results()`, list filters, ordering, pagination and permissions behave exactly as they do today. The script then swaps the new results into the page.

Supports Django 3.2 – 4.2 and Python 3.8+.

## Installation

```bash
pip install django-realtime-search
```

Add it to `INSTALLED_APPS` **before** `django.contrib.admin`:

```python
INSTALLED_APPS = [
    "realtime_search",
    "django.contrib.admin",
    ...
]
```

That's it. Every admin changelist with `search_fields` now searches as you type.

## Configuration

Optional, in `settings.py` (defaults shown):

```python
REALTIME_SEARCH = {
    "ENABLED": True,     # False = only ModelAdmins that opt in get realtime search
    "DEBOUNCE_MS": 300,  # wait this long after the last keystroke before searching
    "MIN_CHARS": 1,      # minimum characters before searching (clearing always searches)
}
```

Per-ModelAdmin overrides:

```python
class BookAdmin(admin.ModelAdmin):
    search_fields = ["title", "author__name"]
    realtime_search = False                      # opt out
    # realtime_search = True                     # opt in (when ENABLED is False)
    # realtime_search = {"DEBOUNCE_MS": 150}     # opt in and override settings
```

## Typed filters (`key:value` in the search box)

Add `SearchFiltersMixin` to a ModelAdmin and list the filters people can type:

```python
from realtime_search.admin import SearchFiltersMixin

@admin.register(Book)
class BookAdmin(SearchFiltersMixin, admin.ModelAdmin):
    search_fields = ["title"]
    search_filters = {
        "author": "author__name",      # key typed in the box -> field path
        "in_print": "in_print",
        "published": "published",
        "year": "published__year",     # explicit lookups/transforms are fine
        "format": "format",            # a field with choices
    }
    # or a list, using the field path as the key: search_filters = ["in_print", "format"]
```

Users can then type things like:

```
parable in_print:no
author:butler year:>=1990
author:"le guin" -format:paperback
```

| Syntax | Meaning |
|---|---|
| `key:value` | Text fields: contains (case-insensitive). Other fields: equals. |
| `key:"two words"` | Quoted value |
| `key:=value` | Exact (case-insensitive for text) |
| `key:^value` | Starts with (text fields) |
| `key:>v` `key:>=v` `key:<v` `key:<=v` | Comparisons: numbers, dates, transforms like `__year` |
| `-key:value` | Exclude matches |

- **Booleans** accept `yes/no`, `true/false`, `1/0`, `on/off`.
- **Choice fields** match the stored value or the label, and a prefix of the label also matches (`format:hard` finds "Hardcover").
- **Dates:** a 4-digit value means the year, so `published:1993` and `published:>1990` work.
- **Combining:** filters AND together, with each other and with any remaining free-text words, which go through `search_fields` as usual.
- **Not recognised:** keys that aren't listed are treated as search text, so `Re:Coded` still searches normally.
- **While typing:** a filter with no value yet (`author:`) is ignored, and a value that can't match (`year:abc`) gives zero results rather than an error.

With realtime search on, the allowed keys appear as clickable hints under the search box. Clicking one adds `key:` to the search.

Only listed keys can be filtered on, and bad field paths are reported by `manage.py check`. The mixin also works without the realtime JavaScript: the filters apply when the search is submitted.

## Behaviour

- **Preserves filters and ordering.** Any active list filters, date hierarchy and sort order stay applied. A new search starts back at page 1.
- **Updates the URL** with `history.replaceState`, so refreshing the page or sharing the link keeps the search.
- **Enter** searches right away. **Escape** clears the search.
- **Stale responses are dropped.** If you keep typing, in-flight requests are cancelled, so results never arrive out of order.
- **Admin actions keep working.** The select-all checkbox and the "N of M selected" counter are re-bound after each update.
- **Protects unsaved `list_editable` edits.** Once a list_editable field has been changed, live updates pause, and pressing Enter does a normal page submit.
- **Fails safe.** If a response isn't a changelist (an error, or a redirect to the login page because the session expired), the browser goes to the URL normally.
- **Accessible.** The result count is announced to screen readers through an `aria-live` region.

After each update, a `realtime-search:updated` event is dispatched on `document` (`event.detail = {query, url}`). Use it to re-initialise any custom JavaScript on the result rows.

## How it hooks in

The app ships an `admin/change_list.html` that extends the next `admin/change_list.html` on the template path (Django supports recursive template extends). It only adds a script and stylesheet to `{% block extrahead %}`. That means it coexists with:

- your own project-level `admin/change_list.html` overrides
- custom `ModelAdmin.change_list_template`s that extend `admin/change_list.html`
- third-party apps that do the same (e.g. django-import-export)

If a template replaces `{% block extrahead %}` without calling `{{ block.super }}`, realtime search won't load on that page.

## Limitations

- Each search is a full changelist request on the server. On very large tables with expensive `search_fields` (e.g. many `__icontains` joins), raise `DEBOUNCE_MS` or `MIN_CHARS`.
- Widgets that need JavaScript initialisation inside `list_editable` rows, such as calendar shortcuts on date fields, aren't re-initialised after an update.

## Development

```bash
pip install -e ".[test]"
playwright install chromium     # optional: enables the browser tests
python runtests.py              # browser tests are skipped if Playwright is missing
tox                             # full Django/Python matrix
```

To try it by hand:

```bash
export REALTIME_SEARCH_DB=demo.sqlite3
django-admin migrate --run-syncdb --settings=tests.settings --pythonpath=.
django-admin seed_demo --count 2000 --settings=tests.settings --pythonpath=.
django-admin runserver --settings=tests.settings --pythonpath=.
# open http://127.0.0.1:8000/admin/testapp/book/  (admin / admin)
```
