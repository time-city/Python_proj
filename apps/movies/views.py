from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from .models import Movie, Review, Genre, UserInteraction
from .services import analyze_sentiment, get_recommendations, semantic_search
from .forms import MovieForm
from django.utils.text import slugify

def home(request):
    """
    Home page displaying movies, genres, and AI Pick of the Day.
    """
    movies = Movie.objects.all().order_by('-created_at')
    
    # AI Pick of the Day: A random movie with rating > 8.0
    ai_pick = Movie.objects.filter(rating__gte=8.0).order_by('?').first()

    # Search (Standard query or Vibe query)
    query = request.GET.get('q')
    vibe = request.GET.get('vibe')
    
    if vibe:
        # Use semantic search for the vibe
        movies = semantic_search(vibe, top_k=24)
        query = vibe # So it shows in the search box
    elif query:
        movies = semantic_search(query, top_k=24)

    # Filter by genre if provided (only if not doing a semantic search, or apply on top)
    genre_slug = request.GET.get('genre')
    if genre_slug:
        movies = movies.filter(genres__slug=genre_slug)
        
    genres = Genre.objects.all()
    
    context = {
        'movies': movies,
        'genres': genres,
        'current_genre': genre_slug,
        'ai_pick': ai_pick,
        'current_vibe': request.GET.get('vibe')
    }
    return render(request, 'movies/home.html', context)

def movie_detail(request, slug):
    """
    Display movie details, reviews, and AI recommendations.
    """
    movie = get_object_or_404(Movie, slug=slug)
    reviews = movie.reviews.all().order_by('-created_at')

    user_id = request.user.id if request.user.is_authenticated else None
    recommendations = get_recommendations(movie_id=movie.id, user_id=user_id, top_n=4)

    context = {
        'movie': movie,
        'reviews': reviews,
        'recommendations': recommendations
    }
    return render(request, 'movies/movie_detail.html', context)

def add_review(request, slug):
    """
    Handle review submission with AI sentiment analysis.
    """
    if request.method == 'POST':
        movie = get_object_or_404(Movie, slug=slug)
        user_name = request.POST.get('user_name')
        if not user_name and request.user.is_authenticated:
            user_name = request.user.username

        comment = request.POST.get('comment')
        rating = request.POST.get('rating')

        if comment and rating:
            sentiment = analyze_sentiment(comment)

            Review.objects.create(
                movie=movie,
                user_name=user_name,
                comment=comment,
                rating=rating,
                sentiment_label=sentiment["label"],
            )

            if request.user.is_authenticated:
                try:
                    rating_val = float(rating)
                except (TypeError, ValueError):
                    rating_val = None
                UserInteraction.objects.update_or_create(
                    user=request.user,
                    movie=movie,
                    defaults={
                        'rating': rating_val,
                        'comment': comment,
                        'sentiment_score': sentiment["score"],
                    },
                )

            messages.success(request, 'Review added!')
        else:
            messages.error(request, 'Please provide both a comment and a rating.')

        return redirect('movie_detail', slug=slug)

    return redirect('home')

def upload_movie(request):
    """
    Handle new movie uploads and generate AI metadata.
    """
    if request.method == 'POST':
        form = MovieForm(request.POST)
        if form.is_valid():
            movie = form.save(commit=False)
            # Automatic Slug
            movie.slug = slugify(movie.title)
            
            # Simple AI Metadata Generation
            if movie.description:
                vibe_keywords = ['action', 'drama', 'sci-fi', 'romance', 'thriller', 'horror', 'funny', 'sad', 'intense']
                tags = [w for w in vibe_keywords if w in movie.description.lower()]
                movie.ai_metadata = f"Generated tags: {', '.join(tags)}. High-quality submission."
            
            movie.save()
            form.save_m2m() # Save genres
            messages.success(request, f'Movie "{movie.title}" uploaded successfully! AI analyzed the content.')
            return redirect('movie_detail', slug=movie.slug)
    else:
        form = MovieForm()
    
    return render(request, 'movies/upload_movie.html', {'form': form})
