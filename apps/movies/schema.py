import graphene
from graphene_django import DjangoObjectType
from .models import Movie, Genre, Review
from .services import semantic_search, get_recommendations, analyze_sentiment
from django.db.models import Prefetch

class GenreType(DjangoObjectType):
    class Meta:
        model = Genre
        fields = ("id", "name", "slug")

class ReviewType(DjangoObjectType):
    class Meta:
        model = Review
        fields = ("id", "movie", "user_name", "comment", "rating", "sentiment_label", "created_at")

class MovieType(DjangoObjectType):
    class Meta:
        model = Movie
        fields = (
            "id", "tmdb_id", "title", "slug", "original_language",
            "description", "poster_path", "release_date", "duration",
            "rating", "trailer_url", "ai_metadata", "genres", "reviews", "created_at"
        )
    
    recommendations = graphene.List(lambda: MovieType, top_n=graphene.Int())

    def resolve_recommendations(self, info, top_n=5):
        return get_recommendations(movie_id=self.id, top_n=top_n)

# --- Mutations ---

class CreateReview(graphene.Mutation):
    class Arguments:
        movie_slug = graphene.String(required=True)
        comment = graphene.String(required=True)
        rating = graphene.Int(required=True)
        user_name = graphene.String() # Optional fallback if not logged in

    review = graphene.Field(ReviewType)
    success = graphene.Boolean()

    def mutate(self, info, movie_slug, comment, rating, user_name=None):
        try:
            movie = Movie.objects.get(slug=movie_slug)
            user = info.context.user
            
            # Use logged in username if available, else provided user_name, else Anonymous
            final_user_name = user_name
            if user.is_authenticated:
                final_user_name = user.username
            elif not final_user_name:
                final_user_name = "Anonymous"

            # AI Sentiment Analysis from services.py
            sentiment = analyze_sentiment(comment)

            review = Review.objects.create(
                movie=movie,
                user_name=final_user_name,
                comment=comment,
                rating=rating,
                sentiment_label=sentiment
            )
            return CreateReview(review=review, success=True)
        except Movie.DoesNotExist:
            raise Exception("Movie not found")

class Mutation(graphene.ObjectType):
    create_review = CreateReview.Field()

# --- Query ---

class Query(graphene.ObjectType):
    movies = graphene.List(MovieType)
    movie = graphene.Field(MovieType, slug=graphene.String(), id=graphene.Int())
    genres = graphene.List(GenreType)
    reviews = graphene.List(ReviewType, movie_slug=graphene.String())
    search_movies = graphene.List(MovieType, query=graphene.String(required=True), top_k=graphene.Int())

    def resolve_movies(self, info):
        # Optimization: prefetch genres to avoid N+1
        return Movie.objects.prefetch_related('genres').all()

    def resolve_movie(self, info, slug=None, id=None):
        # Optimization: prefetch related data
        queryset = Movie.objects.prefetch_related('genres', 'reviews')
        if slug:
            return queryset.filter(slug=slug).first()
        if id:
            return queryset.filter(id=id).first()
        return None

    def resolve_genres(self, info):
        return Genre.objects.all()

    def resolve_reviews(self, info, movie_slug=None):
        # Optimization: select_related movie
        if movie_slug:
            return Review.objects.filter(movie__slug=movie_slug).select_related('movie')
        return Review.objects.select_related('movie').all()

    def resolve_search_movies(self, info, query, top_k=20):
        # AI semantic search (returns QuerySet from FAISS/SentenceTransformer results)
        return semantic_search(query, top_k=top_k)
