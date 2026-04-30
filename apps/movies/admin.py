from django.contrib import admin
from .models import Genre, Movie, Review, UserInteraction

@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ('title', 'release_date', 'rating', 'sentiment_score', 'duration')
    prepopulated_fields = {'slug': ('title',)}
    list_filter = ('genres', 'release_date')
    search_fields = ('title', 'description', 'ai_metadata')

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('movie', 'user_name', 'rating', 'sentiment_label', 'created_at')
    list_filter = ('sentiment_label', 'rating')
    search_fields = ('comment', 'user_name')

@admin.register(UserInteraction)
class UserInteractionAdmin(admin.ModelAdmin):
    list_display = ('user', 'movie', 'rating', 'sentiment_score', 'watched', 'watch_time_pct', 'created_at')
    list_filter = ('watched',)
    search_fields = ('user__username', 'movie__title', 'comment')
    autocomplete_fields = ('movie',)
    raw_id_fields = ('user',)
