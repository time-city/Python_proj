from django.core.management.base import BaseCommand

from apps.movies.models import Movie
from apps.movies.ml_utils import analyze_sentiment


class Command(BaseCommand):
    help = 'Pre-compute sentiment scores for all movies missing one.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Recompute even movies that already have a sentiment_score.',
        )

    def handle(self, *args, **options):
        qs = Movie.objects.all() if options['all'] else Movie.objects.filter(sentiment_score__isnull=True)
        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.WARNING("No movies need sentiment scoring."))
            return

        self.stdout.write(f"Scoring {total} movies...")
        for movie in qs.iterator():
            text = (movie.description or '').strip()
            result = analyze_sentiment(text)
            movie.sentiment_score = result["score"]
            movie.save(update_fields=["sentiment_score"])
            self.stdout.write(f"[{movie.id}] {movie.title}: {result['label']} ({result['score']})")

        self.stdout.write(self.style.SUCCESS(f"Done. Scored {total} movies."))
