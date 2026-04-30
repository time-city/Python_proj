from django.core.management.base import BaseCommand

from apps.movies.services import build_cf_model
from apps.movies.models import UserInteraction


class Command(BaseCommand):
    help = 'Rebuild collaborative-filtering factor matrices from UserInteraction data.'

    def handle(self, *args, **options):
        count = UserInteraction.objects.count()
        if count == 0:
            self.stdout.write(self.style.WARNING("No interactions yet — CF model not built."))
            return

        self.stdout.write(f"Training CF model on {count} interactions...")
        build_cf_model()
        self.stdout.write(self.style.SUCCESS("CF model rebuilt in process memory."))
