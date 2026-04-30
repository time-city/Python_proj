import os
import pickle
import re
from datetime import date

import numpy as np
from scipy.spatial.distance import cdist
from sentence_transformers import SentenceTransformer

from django.db import models
from django.db.models import Q

from .models import Movie, Genre, UserInteraction
from .ml_utils import analyze_sentiment  # re-exported for callers  # noqa: F401

# --- Cached models / embeddings ---
_semantic_model = None
_movie_embeddings = None
_movie_ids = None
_faiss_index = None
_max_rating = None

# --- Collaborative filter factors ---
_user_factors = None
_item_factors = None
_cf_user_index = None
_cf_item_index = None


def get_semantic_model():
    global _semantic_model
    if _semantic_model is None:
        _semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
    return _semantic_model


def load_embeddings():
    global _movie_embeddings, _movie_ids, _faiss_index, _max_rating
    if _movie_embeddings is None or _movie_ids is None:
        filepath = os.path.join('data', 'movie_embeddings.pkl')
        if os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                data = pickle.load(f)
                _movie_ids = data['movie_ids']
                _movie_embeddings = data['embeddings']
                _max_rating = data.get('max_rating', 10.0)
        else:
            _movie_ids = []
            _movie_embeddings = np.array([])

    if _faiss_index is None and len(_movie_ids) > 0:
        try:
            import faiss
            emb = np.array(_movie_embeddings).astype('float32')
            faiss.normalize_L2(emb)
            index = faiss.IndexFlatIP(emb.shape[1])
            index.add(emb)
            _faiss_index = index
            _movie_embeddings = emb
        except ImportError:
            pass

    return _movie_ids, _movie_embeddings, _faiss_index, _max_rating


def semantic_search(query, top_k=20):
    if not query:
        return Movie.objects.none()

    keyword_qs = Movie.objects.filter(
        Q(title__icontains=query) |
        Q(description__icontains=query) |
        Q(ai_metadata__icontains=query)
    )
    keyword_ids = list(keyword_qs.values_list('id', flat=True))

    model = get_semantic_model()
    ids, embeddings, _, __ = load_embeddings()

    if len(ids) == 0:
        return keyword_qs

    query_embedding = model.encode([query])
    distances = cdist(query_embedding, embeddings, metric='cosine')[0]
    top_indices = np.argsort(distances)[:top_k]
    semantic_ids = [ids[idx] for idx in top_indices]

    seen = set(keyword_ids)
    merged_ids = list(keyword_ids)
    for mid in semantic_ids:
        if mid not in seen:
            seen.add(mid)
            merged_ids.append(mid)

    preserved_order = models.Case(
        *[models.When(pk=pk, then=pos) for pos, pk in enumerate(merged_ids)]
    )
    return Movie.objects.filter(id__in=merged_ids).order_by(preserved_order)


def calculate_similarity(text1, text2):
    """Jaccard similarity between two texts — used by the genre fallback path."""
    if not text1 or not text2:
        return 0.0

    def tokenize(text):
        return set(re.findall(r'\w+', text.lower()))

    tokens1 = tokenize(text1)
    tokens2 = tokenize(text2)
    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)
    return intersection / union if union > 0 else 0.0


# =========================================================================
# Collaborative filtering (matrix factorisation via TruncatedSVD)
# =========================================================================

def build_cf_model():
    """Rebuild user/item factor matrices. Call nightly or from a management command."""
    global _user_factors, _item_factors, _cf_user_index, _cf_item_index

    interactions = list(UserInteraction.objects.values_list(
        'user_id', 'movie_id', 'rating', 'watch_time_pct', 'sentiment_score'
    ))

    if not interactions:
        _user_factors = _item_factors = _cf_user_index = _cf_item_index = None
        return

    user_ids = sorted({r[0] for r in interactions})
    movie_ids = sorted({r[1] for r in interactions})
    _cf_user_index = {uid: i for i, uid in enumerate(user_ids)}
    _cf_item_index = {mid: i for i, mid in enumerate(movie_ids)}

    rows, cols, data = [], [], []
    for uid, mid, rating, watch_pct, sentiment in interactions:
        if rating is not None and sentiment is not None:
            score = (rating / 10.0) * 0.7 + sentiment * 0.3
        elif rating is not None:
            score = rating / 10.0
        elif sentiment is not None:
            score = sentiment
        else:
            score = (watch_pct or 0.0) * 0.7

        rows.append(_cf_user_index[uid])
        cols.append(_cf_item_index[mid])
        data.append(score)

    from scipy.sparse import csr_matrix
    from sklearn.decomposition import TruncatedSVD

    matrix = csr_matrix((data, (rows, cols)), shape=(len(user_ids), len(movie_ids)))
    n_components = min(50, min(matrix.shape) - 1) if min(matrix.shape) > 1 else 1
    svd = TruncatedSVD(n_components=max(1, n_components), random_state=42)
    _user_factors = svd.fit_transform(matrix)
    _item_factors = svd.components_.T


def ensure_cf_model():
    """Lazy-train CF model the first time it is needed in this process."""
    if _user_factors is None and UserInteraction.objects.exists():
        build_cf_model()


def get_collaborative_recommendations(user_id, top_k=20):
    ensure_cf_model()
    if _user_factors is None or _cf_user_index is None or user_id not in _cf_user_index:
        return []

    u_idx = _cf_user_index[user_id]
    user_vec = _user_factors[u_idx]
    scores = _item_factors @ user_vec
    top_indices = np.argsort(scores)[::-1][:top_k]

    movie_id_list = list(_cf_item_index.keys())
    return [movie_id_list[i] for i in top_indices]


# =========================================================================
# Score fusion & public API
# =========================================================================

def _content_scores_for(movie_id, top_n):
    """Return {movie_id: cosine_sim} from FAISS for a given seed movie."""
    scores = {}
    if not movie_id:
        return scores

    ids, embeddings, index, _ = load_embeddings()
    if index is None or movie_id not in ids:
        return scores

    import faiss
    idx = ids.index(movie_id)
    q = np.asarray(embeddings[idx]).reshape(1, -1).astype('float32').copy()
    faiss.normalize_L2(q)
    sims, fidxs = index.search(q, top_n * 4)
    for sim, fidx in zip(sims[0], fidxs[0]):
        if fidx >= 0 and ids[fidx] != movie_id:
            scores[ids[fidx]] = float(sim)
    return scores


def get_hybrid_recommendations(movie_id=None, user_id=None, top_n=10):
    """
    Three-way weighted fusion. Weights are chosen by intent:
      - Seed movie given ("similar to this") → content dominates, CF only re-ranks
        the content pool. Prevents CF from pulling in globally-liked but unrelated items.
      - No seed (home feed)                  → CF dominates, content nudges.
    """
    if movie_id:
        # "Similar to this movie" intent — content is primary, CF is the personalization layer
        ALPHA, BETA, GAMMA = 0.25, 0.60, 0.15
        seed_provided = True
    else:
        # "For you" feed intent — CF is primary, content scores are 0 anyway (no seed)
        ALPHA, BETA, GAMMA = 0.55, 0.30, 0.15
        seed_provided = False

    content_scores = _content_scores_for(movie_id, top_n)

    cf_scores = {}
    if user_id:
        cf_ids = get_collaborative_recommendations(user_id, top_k=top_n * 4)
        n = len(cf_ids)
        for rank, mid in enumerate(cf_ids):
            cf_scores[mid] = 1.0 - rank / n if n else 0.0

    # Build the exclude set: seed movie + everything user has already interacted with
    exclude_ids = set()
    if movie_id:
        exclude_ids.add(movie_id)
    if user_id:
        exclude_ids.update(
            UserInteraction.objects.filter(user_id=user_id)
            .values_list('movie_id', flat=True)
        )

    # Candidate pool depends on intent:
    # - With seed: only movies similar to seed (content pool). CF re-ranks within.
    # - Without seed: union of CF picks + (empty) content pool.
    if seed_provided:
        all_ids = set(content_scores) - exclude_ids
    else:
        all_ids = (set(content_scores) | set(cf_scores)) - exclude_ids

    if not all_ids:
        qs = Movie.objects.exclude(id__in=exclude_ids) if exclude_ids else Movie.objects.all()
        return list(qs.order_by('-rating')[:top_n])

    results = []
    today = date.today()
    for mid in all_ids:
        try:
            movie = Movie.objects.get(id=mid)
        except Movie.DoesNotExist:
            continue

        c_score = content_scores.get(mid, 0.0)
        cf_score = cf_scores.get(mid, 0.0)

        sentiment = movie.sentiment_score if movie.sentiment_score is not None else 0.5
        raw_rating = float(movie.rating or 0) / 10.0
        s_score = raw_rating * (0.5 + sentiment)

        recency = 0.0
        if movie.release_date:
            age_years = (today - movie.release_date).days / 365
            recency = max(0.0, 1.0 - age_years / 30)

        final = ALPHA * cf_score + BETA * c_score + GAMMA * s_score + 0.05 * recency
        results.append((movie, final))

    results.sort(key=lambda x: x[1], reverse=True)

    # Diversity re-ranking — avoid one-genre dominance
    seen_genres = set()
    diverse = []
    remainder = []
    for movie, _score in results:
        genres = set(movie.genres.values_list('id', flat=True))
        if not genres & seen_genres:
            diverse.append(movie)
            seen_genres |= genres
        else:
            remainder.append(movie)
        if len(diverse) >= top_n:
            break

    if len(diverse) < top_n:
        diverse.extend(remainder[:top_n - len(diverse)])
    return diverse[:top_n]


def get_user_feed(user_id, top_n=24):
    """
    Personalized home feed.
    Strategy: take user's top-3 highest-rated movies as seeds, fan out via hybrid
    recs from each, then merge unique candidates by best score.

    Cold-start fallback: popular by genres user has already engaged with, then
    overall top-rated. Returns at most top_n movies, deduped.
    """
    if not user_id:
        return list(Movie.objects.order_by('-rating')[:top_n])

    interactions = UserInteraction.objects.filter(user_id=user_id)
    interaction_count = interactions.count()

    if interaction_count == 0:
        return list(Movie.objects.order_by('-rating')[:top_n])

    seen_movie_ids = set(interactions.values_list('movie_id', flat=True))

    # Pick up to 3 seed movies the user rated highly (≥7) — fall back to anything they engaged with
    seeds = list(
        interactions.filter(rating__gte=7).order_by('-rating', '-created_at')[:3]
        .values_list('movie_id', flat=True)
    )
    if not seeds:
        seeds = list(interactions.order_by('-created_at')[:3].values_list('movie_id', flat=True))

    # Fan out: hybrid recs from each seed
    candidates = {}
    for seed_id in seeds:
        recs = get_hybrid_recommendations(
            movie_id=seed_id, user_id=user_id, top_n=top_n
        )
        for rank, m in enumerate(recs):
            score = 1.0 - rank / max(len(recs), 1)
            if m.id in seen_movie_ids:
                continue
            candidates[m.id] = max(candidates.get(m.id, 0.0), score)

    # If no seeds (shouldn't happen given guard above) or empty candidates,
    # fall back to genre-based popularity from user's liked genres.
    if not candidates:
        liked_genre_ids = list(
            Genre.objects.filter(movies__id__in=seen_movie_ids)
            .values_list('id', flat=True).distinct()
        )
        qs = (Movie.objects.filter(genres__in=liked_genre_ids)
              .exclude(id__in=seen_movie_ids)
              .distinct().order_by('-rating'))
        return list(qs[:top_n])

    # Sort merged candidates and fetch movies
    sorted_ids = [mid for mid, _ in sorted(candidates.items(), key=lambda x: x[1], reverse=True)]
    movies_by_id = {m.id: m for m in Movie.objects.filter(id__in=sorted_ids[:top_n]).prefetch_related('genres')}
    return [movies_by_id[mid] for mid in sorted_ids[:top_n] if mid in movies_by_id]


def get_recommendations(movie_id=None, user_id=None, top_n=5):
    """
    Public API. Staged cold-start fallback based on how much user data exists.
    """
    if user_id:
        interaction_count = UserInteraction.objects.filter(user_id=user_id).count()

        if interaction_count == 0:
            if movie_id:
                return get_hybrid_recommendations(movie_id=movie_id, user_id=None, top_n=top_n)
            return list(Movie.objects.order_by('-rating')[:top_n])

        if interaction_count < 5:
            return get_hybrid_recommendations(movie_id=movie_id, user_id=None, top_n=top_n)

    # No user context at all → pure content path, identical to prior behaviour
    if not user_id and movie_id:
        return _content_only_recommendations(movie_id, top_n)

    return get_hybrid_recommendations(movie_id=movie_id, user_id=user_id, top_n=top_n)


def _content_only_recommendations(movie_id, top_n):
    """Legacy content-only path — 0.7*cosine + 0.3*(rating/max) with Jaccard fallback."""
    try:
        target_movie = Movie.objects.get(id=movie_id)
    except Movie.DoesNotExist:
        return []

    ids, embeddings, index, max_rating = load_embeddings()

    if index is not None and movie_id in ids:
        import faiss

        idx = ids.index(movie_id)
        query_vec = np.asarray(embeddings[idx]).reshape(1, -1).astype('float32').copy()
        faiss.normalize_L2(query_vec)

        n_search = top_n + 1
        similarity_scores, faiss_indices = index.search(query_vec, n_search)
        similarity_scores = similarity_scores[0]
        faiss_indices = faiss_indices[0]

        max_rating = max_rating or 10.0

        weighted = []
        for faiss_idx, sim_score in zip(faiss_indices, similarity_scores):
            if faiss_idx < 0 or faiss_idx >= len(ids):
                continue
            candidate_id = ids[faiss_idx]
            if candidate_id == movie_id:
                continue
            try:
                candidate = Movie.objects.get(id=candidate_id)
            except Movie.DoesNotExist:
                continue
            rating_score = float(candidate.rating or 0) / float(max_rating)
            final_score = 0.7 * float(sim_score) + 0.3 * rating_score
            weighted.append((candidate, final_score))

        weighted.sort(key=lambda x: x[1], reverse=True)
        recommendations = [item[0] for item in weighted[:top_n]]

        if len(recommendations) < top_n:
            exclude_ids = [m.id for m in recommendations] + [movie_id]
            others = Movie.objects.exclude(id__in=exclude_ids).order_by('-rating')[:top_n - len(recommendations)]
            recommendations.extend(others)

        return recommendations

    # Genre + Jaccard fallback
    target_genres = target_movie.genres.all()
    candidates = Movie.objects.filter(genres__in=target_genres).exclude(id=movie_id).distinct()

    target_meta = f"{target_movie.title} {target_movie.ai_metadata or ''}"
    scored = []
    for candidate in candidates:
        candidate_meta = f"{candidate.title} {candidate.ai_metadata or ''}"
        similarity = calculate_similarity(target_meta, candidate_meta)
        score = similarity * (float(candidate.rating) or 5.0)
        scored.append((candidate, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    recommendations = [item[0] for item in scored[:top_n]]

    if len(recommendations) < top_n:
        exclude_ids = [m.id for m in recommendations] + [movie_id]
        others = Movie.objects.exclude(id__in=exclude_ids).order_by('-rating')[:top_n - len(recommendations)]
        recommendations.extend(others)

    return recommendations
