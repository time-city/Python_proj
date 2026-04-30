import graphene
from graphene_django import DjangoObjectType

from .models import Movie, Genre, Review, UserInteraction
from .services import semantic_search, get_recommendations, analyze_sentiment


class GenreType(DjangoObjectType):
    class Meta:
        model = Genre
        fields = ("id", "name", "slug")


class ReviewType(DjangoObjectType):
    class Meta:
        model = Review
        fields = ("id", "movie", "user_name", "comment", "rating", "sentiment_label", "created_at")


class UserInteractionType(DjangoObjectType):
    class Meta:
        model = UserInteraction
        fields = (
            "id", "user", "movie", "rating", "comment",
            "sentiment_score", "watched", "watch_time_pct", "created_at",
        )


class MovieType(DjangoObjectType):
    class Meta:
        model = Movie
        fields = (
            "id", "tmdb_id", "title", "slug", "original_language",
            "description", "poster_path", "release_date", "duration",
            "rating", "trailer_url", "ai_metadata", "sentiment_score",
            "genres", "reviews", "created_at",
        )

    recommendations = graphene.List(lambda: MovieType, top_n=graphene.Int())

    def resolve_recommendations(self, info, top_n=5):
        user = getattr(info.context, "user", None)
        user_id = user.id if user and user.is_authenticated else None
        return get_recommendations(movie_id=self.id, user_id=user_id, top_n=top_n)


# --- Mutations ---

class CreateReview(graphene.Mutation):
    class Arguments:
        movie_slug = graphene.String(required=True)
        comment = graphene.String()
        rating = graphene.Int()
        user_name = graphene.String()

    review = graphene.Field(ReviewType)
    interaction = graphene.Field(UserInteractionType)
    success = graphene.Boolean()

    def mutate(self, info, movie_slug, comment=None, rating=None, user_name=None):
        comment = (comment or "").strip() or None
        if not comment and rating is None:
            raise Exception("Provide a comment, a rating, or both.")

        try:
            movie = Movie.objects.get(slug=movie_slug)
        except Movie.DoesNotExist:
            raise Exception("Movie not found")

        user = info.context.user
        final_user_name = user_name
        if user.is_authenticated:
            final_user_name = user.username
        elif not final_user_name:
            final_user_name = "Anonymous"

        sentiment = analyze_sentiment(comment) if comment else None

        review = Review.objects.create(
            movie=movie,
            user_name=final_user_name,
            comment=comment,
            rating=rating,
            sentiment_label=sentiment["label"] if sentiment else None,
        )

        interaction = None
        if user.is_authenticated:
            interaction, _ = UserInteraction.objects.update_or_create(
                user=user,
                movie=movie,
                defaults={
                    "rating": float(rating) if rating is not None else None,
                    "comment": comment,
                    "sentiment_score": sentiment["score"] if sentiment else None,
                },
            )

        return CreateReview(review=review, interaction=interaction, success=True)


class RecordInteraction(graphene.Mutation):
    """Lightweight signal recorder — used for star ratings, watch progress, etc."""
    class Arguments:
        movie_slug = graphene.String(required=True)
        rating = graphene.Float()
        comment = graphene.String()
        watched = graphene.Boolean()
        watch_time_pct = graphene.Float()

    interaction = graphene.Field(UserInteractionType)
    success = graphene.Boolean()

    def mutate(self, info, movie_slug, rating=None, comment=None,
               watched=None, watch_time_pct=None):
        user = info.context.user
        if not user.is_authenticated:
            raise Exception("Authentication required")

        try:
            movie = Movie.objects.get(slug=movie_slug)
        except Movie.DoesNotExist:
            raise Exception("Movie not found")

        defaults = {}
        if rating is not None:
            defaults["rating"] = rating
        if comment is not None:
            defaults["comment"] = comment
            defaults["sentiment_score"] = analyze_sentiment(comment)["score"]
        if watched is not None:
            defaults["watched"] = watched
        if watch_time_pct is not None:
            defaults["watch_time_pct"] = watch_time_pct

        interaction, _ = UserInteraction.objects.update_or_create(
            user=user, movie=movie, defaults=defaults,
        )
        return RecordInteraction(interaction=interaction, success=True)


class Mutation(graphene.ObjectType):
    create_review = CreateReview.Field()
    record_interaction = RecordInteraction.Field()


# --- Query ---

class Query(graphene.ObjectType):
    movies = graphene.List(MovieType)
    movie = graphene.Field(MovieType, slug=graphene.String(), id=graphene.Int())
    genres = graphene.List(GenreType)
    reviews = graphene.List(ReviewType, movie_slug=graphene.String())
    search_movies = graphene.List(MovieType, query=graphene.String(required=True), top_k=graphene.Int())
    my_recommendations = graphene.List(MovieType, top_n=graphene.Int(), seed_movie_slug=graphene.String())
    my_interactions = graphene.List(UserInteractionType)

    def resolve_movies(self, info):
        return Movie.objects.prefetch_related('genres').all()

    def resolve_movie(self, info, slug=None, id=None):
        queryset = Movie.objects.prefetch_related('genres', 'reviews')
        if slug:
            return queryset.filter(slug=slug).first()
        if id:
            return queryset.filter(id=id).first()
        return None

    def resolve_genres(self, info):
        return Genre.objects.all()

    def resolve_reviews(self, info, movie_slug=None):
        if movie_slug:
            return Review.objects.filter(movie__slug=movie_slug).select_related('movie')
        return Review.objects.select_related('movie').all()

    def resolve_search_movies(self, info, query, top_k=20):
        return semantic_search(query, top_k=top_k)

    def resolve_my_recommendations(self, info, top_n=10, seed_movie_slug=None):
        user = getattr(info.context, "user", None)
        user_id = user.id if user and user.is_authenticated else None

        seed_movie_id = None
        if seed_movie_slug:
            seed = Movie.objects.filter(slug=seed_movie_slug).only("id").first()
            if seed:
                seed_movie_id = seed.id

        return get_recommendations(movie_id=seed_movie_id, user_id=user_id, top_n=top_n)

    def resolve_my_interactions(self, info):
        user = info.context.user
        if not user.is_authenticated:
            return UserInteraction.objects.none()
        return UserInteraction.objects.filter(user=user).select_related("movie")
