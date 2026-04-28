from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

class Genre(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)

    class Meta:
        db_table = 'genres'

    def __str__(self):
        return self.name

class Movie(models.Model):
    tmdb_id = models.IntegerField(unique=True, null=True, blank=True, help_text="Origin TMDB ID")
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    original_language = models.CharField(max_length=20, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    poster_path = models.CharField(max_length=500, null=True, blank=True)
    release_date = models.DateField(null=True, blank=True)
    duration = models.IntegerField(help_text="Duration in minutes", null=True, blank=True)
    rating = models.DecimalField(max_digits=4, decimal_places=1, default=0.0)
    
    trailer_url = models.CharField(max_length=500, null=True, blank=True)
    # AI Metadata for filtering/recommendation
    ai_metadata = models.TextField(null=True, blank=True, help_text="AI generated tags and features")
    sentiment_score = models.FloatField(null=True, blank=True, help_text="0.0 negative .. 0.5 neutral .. 1.0 positive")

    genres = models.ManyToManyField(Genre, related_name='movies', db_table='movie_genres')
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'movies'

    def __str__(self):
        return self.title

class Review(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='reviews')
    user_name = models.CharField(max_length=100)
    comment = models.TextField(null=True, blank=True)
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        null=True, blank=True
    )
    # AI Sentiment Analysis Result
    sentiment_label = models.CharField(max_length=20, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reviews'
        constraints = [
            models.CheckConstraint(
                check=models.Q(rating__gte=1) & models.Q(rating__lte=10),
                name='rating_range'
            )
        ]

    def __str__(self):
        return f"{self.user_name} on {self.movie.title}"


class UserInteraction(models.Model):
    """Signals collected from authenticated users — drives collaborative filtering."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='interactions')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='interactions')

    rating = models.FloatField(null=True, blank=True)
    comment = models.TextField(null=True, blank=True)
    sentiment_score = models.FloatField(null=True, blank=True)

    watched = models.BooleanField(default=False)
    watch_time_pct = models.FloatField(default=0.0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_interactions'
        unique_together = ('user', 'movie')

    def __str__(self):
        return f"{self.user_id} → {self.movie_id}"
