"""
Seed realistic test data for evaluating the recommender end-to-end.

Creates:
- N test users grouped into M "taste clusters" (each cluster favors certain genres)
- Each user rates 5-30 movies, weighted toward their cluster's preferred genres
- A configurable fraction of ratings include comments (drives sentiment pipeline)
- Triggers signals → sentiment_score auto-populated

Usage:
    python manage.py seed_test_data --users 50
    python manage.py seed_test_data --users 100 --min-ratings 8 --max-ratings 40
    python manage.py seed_test_data --reset            # wipe previously-seeded test data
    python manage.py seed_test_data --users 50 --reset # wipe + reseed
"""

import random
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User
from apps.movies.models import Movie, Genre, UserInteraction, Review


TEST_USER_PREFIX = "testuser_"
TEST_USER_PASSWORD = "testpass123"


# Realistic comment templates per sentiment class.
POSITIVE_COMMENTS = [
    "Absolutely loved this. A must-watch.",
    "Brilliant cinematography and acting throughout.",
    "Mind-blowing from start to finish.",
    "One of the best films I've seen this year.",
    "Genuinely moving and beautifully shot.",
    "Captivating story, strong performances.",
    "I was glued to the screen the whole time.",
    "Fantastic pacing and emotional depth.",
    "Highly recommend, will watch again.",
    "A masterpiece. Wonderful direction.",
    "Loved every minute of it.",
    "Surprisingly good, exceeded my expectations.",
    "Excellent script and great chemistry between leads.",
]

NEGATIVE_COMMENTS = [
    "Boring and predictable. Waste of time.",
    "Couldn't even finish it. Painfully slow.",
    "Terrible writing, weak performances.",
    "I hated almost everything about this.",
    "Disappointing and forgettable.",
    "The plot makes no sense.",
    "Awful pacing, dragged on forever.",
    "Stupid characters making stupid decisions.",
    "One of the worst films I've ever seen.",
    "Total trash, do not recommend.",
    "Horrible dialogue and lazy writing.",
    "Skip it. Not worth your time.",
]

NEUTRAL_COMMENTS = [
    "It was okay. Nothing special.",
    "Decent but forgettable.",
    "Watchable, but I won't revisit it.",
    "Average. Has moments but nothing stands out.",
    "Not bad, not great.",
    "Fine for a one-time watch.",
    "Mediocre overall.",
]


def comment_for_rating(rating):
    """Return a realistic comment whose tone matches the rating."""
    if rating >= 8:
        return random.choice(POSITIVE_COMMENTS)
    if rating <= 4:
        return random.choice(NEGATIVE_COMMENTS)
    return random.choice(NEUTRAL_COMMENTS)


class Command(BaseCommand):
    help = "Seed test users + interactions to exercise the recommender (CF, sentiment, hybrid)."

    def add_arguments(self, parser):
        parser.add_argument('--users', type=int, default=50,
                            help='Number of test users to create (default 50).')
        parser.add_argument('--min-ratings', type=int, default=5,
                            help='Minimum interactions per user (default 5 — CF threshold).')
        parser.add_argument('--max-ratings', type=int, default=25,
                            help='Maximum interactions per user (default 25).')
        parser.add_argument('--comment-prob', type=float, default=0.5,
                            help='Probability that a rating also has a comment (default 0.5).')
        parser.add_argument('--pool-size', type=int, default=400,
                            help='How many movies to draw from (top-rated). Smaller pool = more user overlap = better CF signal.')
        parser.add_argument('--reset', action='store_true',
                            help='Delete previously-seeded test users (and their interactions/reviews) before seeding.')

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts['reset']:
            self._reset()

        n_users = opts['users']
        if n_users == 0:
            self.stdout.write(self.style.WARNING("--users 0 → only reset, nothing to seed."))
            return

        movie_pool = self._build_movie_pool(opts['pool_size'])
        if not movie_pool:
            self.stdout.write(self.style.ERROR("No movies in DB. Import movies first."))
            return

        clusters = self._build_genre_clusters(movie_pool)
        self.stdout.write(f"Built {len(clusters)} taste clusters from genre data.")
        for name, info in clusters.items():
            self.stdout.write(f"  · {name}: {len(info['preferred'])} preferred / {len(info['avoid'])} avoid")

        existing = User.objects.filter(username__startswith=TEST_USER_PREFIX).count()
        next_index = existing + 1

        users_created = 0
        interactions_created = 0
        reviews_created = 0

        cluster_names = list(clusters.keys())

        for i in range(n_users):
            username = f"{TEST_USER_PREFIX}{next_index + i:04d}"
            cluster_name = random.choice(cluster_names)
            cluster = clusters[cluster_name]

            user = User.objects.create_user(
                username=username,
                password=TEST_USER_PASSWORD,
                email=f"{username}@test.local",
                role="STUDENT",
            )
            users_created += 1

            n_ratings = random.randint(opts['min_ratings'], opts['max_ratings'])
            sampled = self._sample_for_user(cluster, movie_pool, n_ratings)

            for movie, is_preferred in sampled:
                rating = self._rating_for(is_preferred)
                with_comment = random.random() < opts['comment_prob']
                comment = comment_for_rating(rating) if with_comment else None

                # Public review row (anonymous-style; signal auto-fills sentiment_label)
                Review.objects.create(
                    movie=movie,
                    user_name=user.username,
                    comment=comment,
                    rating=rating,
                )
                reviews_created += 1

                # Authenticated interaction (signal auto-fills sentiment_score)
                UserInteraction.objects.update_or_create(
                    user=user,
                    movie=movie,
                    defaults={
                        'rating': float(rating),
                        'comment': comment,
                        # sentiment_score left NULL → signal computes from comment
                    },
                )
                interactions_created += 1

            if (i + 1) % 10 == 0:
                self.stdout.write(f"  seeded {i + 1}/{n_users} users")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone.\n"
            f"  users created     : {users_created}\n"
            f"  reviews created   : {reviews_created}\n"
            f"  interactions      : {interactions_created}\n"
            f"  password (all)    : {TEST_USER_PASSWORD}\n"
            f"\nNext steps:\n"
            f"  1. python manage.py runserver\n"
            f"  2. log in as {TEST_USER_PREFIX}0001 (or any seeded user) and check /movies/<slug>/\n"
            f"  3. CF will auto-train on first request that reaches the hybrid path"
        ))

    # ---------- internals ----------

    def _reset(self):
        qs = User.objects.filter(username__startswith=TEST_USER_PREFIX)
        n = qs.count()
        if n == 0:
            self.stdout.write("No previously-seeded test users found.")
            return

        usernames = list(qs.values_list('username', flat=True))
        # Delete reviews referencing these synthetic users (Review.user_name is a CharField, so manual)
        Review.objects.filter(user_name__in=usernames).delete()
        # UserInteraction has FK on_delete=CASCADE, so deleting the user wipes interactions too.
        qs.delete()
        self.stdout.write(self.style.WARNING(f"Reset: deleted {n} test users + their reviews/interactions."))

    def _build_movie_pool(self, pool_size):
        """Top-rated movies. Smaller pool = more inter-user overlap = stronger CF signal."""
        return list(
            Movie.objects.exclude(rating__isnull=True)
            .order_by('-rating', 'id')[:pool_size]
            .prefetch_related('genres')
        )

    def _build_genre_clusters(self, movies):
        """
        Define ~5 taste clusters by picking dominant genres.
        Each cluster has 'preferred' genre_ids and 'avoid' genre_ids.
        """
        # Discover genres that actually appear in the pool, ranked by frequency
        freq = {}
        for m in movies:
            for g in m.genres.all():
                freq[g.id] = freq.get(g.id, 0) + 1

        if not freq:
            # Fallback: one cluster, no preferences — purely random ratings
            return {"generalist": {"preferred": set(), "avoid": set()}}

        sorted_genres = sorted(freq.keys(), key=lambda gid: -freq[gid])
        top = sorted_genres[:8]  # work with the 8 most common genres

        # Hand-tune 5 clusters by partitioning these genres
        # (uses indices into `top`, not actual ids — works for any genre taxonomy)
        clusters = {}
        n = len(top)
        if n >= 6:
            clusters['action_fan']    = {'preferred': {top[0], top[2]}, 'avoid': {top[5]}}
            clusters['drama_fan']     = {'preferred': {top[1], top[4]}, 'avoid': {top[0]}}
            clusters['comedy_fan']    = {'preferred': {top[3]},          'avoid': {top[5]}}
            clusters['arthouse_fan']  = {'preferred': {top[4], top[5]},  'avoid': {top[0], top[2]}}
            clusters['generalist']    = {'preferred': set(top[:4]),      'avoid': set()}
        else:
            # Smaller taxonomy — split simpler
            half = n // 2
            clusters['cluster_a'] = {'preferred': set(top[:half]), 'avoid': set(top[half:])}
            clusters['cluster_b'] = {'preferred': set(top[half:]), 'avoid': set(top[:half])}
            clusters['generalist'] = {'preferred': set(top), 'avoid': set()}

        return clusters

    def _sample_for_user(self, cluster, movies, n):
        """
        Pick n movies for this user. Bias toward `preferred` genres.
        Returns list of (movie, is_preferred_bool).
        """
        preferred_ids = cluster['preferred']
        avoid_ids = cluster['avoid']

        preferred_movies = [m for m in movies if any(g.id in preferred_ids for g in m.genres.all())]
        neutral_movies = [m for m in movies if m not in preferred_movies and not any(g.id in avoid_ids for g in m.genres.all())]
        avoid_movies = [m for m in movies if any(g.id in avoid_ids for g in m.genres.all())]

        # Mix: ~60% preferred, ~30% neutral, ~10% disliked (to give negative ratings signal)
        n_pref = int(n * 0.6)
        n_neu = int(n * 0.3)
        n_avoid = n - n_pref - n_neu

        picked = []
        picked += [(m, True) for m in random.sample(preferred_movies, min(n_pref, len(preferred_movies)))]
        picked += [(m, None) for m in random.sample(neutral_movies, min(n_neu, len(neutral_movies)))]
        picked += [(m, False) for m in random.sample(avoid_movies, min(n_avoid, len(avoid_movies)))]

        # If any bucket was empty, top up from the whole pool
        if len(picked) < n:
            seen = {p[0].id for p in picked}
            extras = [m for m in movies if m.id not in seen]
            random.shuffle(extras)
            for m in extras[:n - len(picked)]:
                picked.append((m, None))

        random.shuffle(picked)
        return picked

    def _rating_for(self, is_preferred):
        """is_preferred=True → 7-10, False → 1-4, None → 4-7 (lukewarm)."""
        if is_preferred is True:
            return random.choice([7, 8, 8, 9, 9, 9, 10])
        if is_preferred is False:
            return random.choice([1, 2, 3, 3, 4, 4])
        return random.choice([4, 5, 5, 6, 6, 7])
