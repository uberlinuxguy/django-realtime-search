import datetime
import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from tests.testapp.models import Author, Book

AUTHORS = ["Ursula K. Le Guin", "Octavia Butler", "Terry Pratchett", "Iain M. Banks", "N. K. Jemisin"]
WORDS = ["Dark", "Left", "Hand", "Parable", "Sower", "Guards", "Night", "Player", "Games",
         "Broken", "Earth", "Fifth", "Season", "Small", "Gods", "Lathe", "Heaven", "Wild", "Seed"]


class Command(BaseCommand):
    help = "Create an admin/admin superuser and replace all books with demo data."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=200, help="Number of books to create.")

    def handle(self, *args, **options):
        User = get_user_model()
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin")
        rng = random.Random(1)
        authors = [Author.objects.get_or_create(name=n)[0] for n in AUTHORS]
        Book.objects.all().delete()
        Book.objects.bulk_create(
            Book(
                title=" ".join(rng.sample(WORDS, 3)),
                author=rng.choice(authors),
                published=datetime.date(1960, 1, 1) + datetime.timedelta(days=rng.randrange(60 * 365)),
                in_print=rng.random() > 0.3,
                format=rng.choice(["hc", "pb", "eb"]),
            )
            for _ in range(options["count"])
        )
        self.stdout.write("Seeded %d books. Log in as admin / admin." % options["count"])
