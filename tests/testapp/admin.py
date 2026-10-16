from django.contrib import admin

from realtime_search.admin import SearchFiltersMixin

from .models import Author, Book, Genre, Publisher, Tag


@admin.register(Book)
class BookAdmin(SearchFiltersMixin, admin.ModelAdmin):
    list_display = ["title", "author", "published", "in_print", "format"]
    list_filter = ["in_print"]
    search_fields = ["title", "author__name"]
    date_hierarchy = "published"
    list_per_page = 10
    search_filters = {
        "author": "author__name",
        "in_print": "in_print",
        "published": "published",
        "year": "published__year",
        "format": "format",
    }


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    search_fields = ["name"]
    realtime_search = {"DEBOUNCE_MS": 100, "MIN_CHARS": 2}


@admin.register(Publisher)
class PublisherAdmin(admin.ModelAdmin):
    pass


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    search_fields = ["name"]
    realtime_search = False


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    search_fields = ["name"]
    change_list_template = "testapp/custom_change_list.html"
