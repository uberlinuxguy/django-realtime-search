from django.db import models


class Author(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Book(models.Model):
    title = models.CharField(max_length=200)
    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    published = models.DateField()
    in_print = models.BooleanField(default=True)
    format = models.CharField(
        max_length=2,
        choices=[("hc", "Hardcover"), ("pb", "Paperback"), ("eb", "E-book")],
        default="pb",
    )

    def __str__(self):
        return self.title


class Publisher(models.Model):
    """Admin has no search_fields."""

    name = models.CharField(max_length=100)


class Tag(models.Model):
    """Admin opts out of realtime search."""

    name = models.CharField(max_length=50)


class Genre(models.Model):
    """Admin uses a custom changelist template."""

    name = models.CharField(max_length=50)
