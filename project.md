# Intelligent Movie Recommendation System

Based on the current architecture and codebase, this project is an **AI-powered Movie Recommendation Web Application** built on the Django framework. While legacy files (e.g., portions of `README.md` and `db_models.py`) suggest a foundation from a Student Management System, the active and developed features are entirely centered around movie data and machine learning.

Here is a breakdown of the system architecture across Frontend, Backend, and Database layers:

## 1. Frontend (FE)
The frontend utilizes **Server-Side Rendering (SSR)** through Django Templates, providing a fast, SEO-friendly interface.
*   **Technology Stack**: HTML, CSS, and the Django Template Language. It leverages Bootstrap 5 (inferred from legacy configurations and standard layouts) to build responsive UI components.
*   **Key Views & Templates**:
    *   `templates/base.html`: The master layout template that includes the navigation bar, structural shell, and asset imports.
    *   `templates/movies/home.html`: The primary dashboard where users can browse movies, use genre filters, and interact with the AI-powered semantic search bar.
    *   `templates/movies/movie_detail.html`: The detail page for an individual movie. It displays metadata, promotional assets, user reviews, and an AI-curated "Similar Movies" section.

## 2. Backend (BE)
The backend is powered by **Django** alongside integrated Machine Learning libraries (`sentence-transformers`, `scikit-learn`, `numpy`) for advanced data processing. The system is cleanly organized into functional apps:

*   **`apps/accounts`**: Handles standard authentication, user permissions, session management, and login/register interfaces.
*   **`apps/movies`**: The central application module driving the movie features.
    *   **Views (`views.py`)**: Manages routing and context generation for the `home` view, the `movie_detail` view, and handles `add_review` POST submissions.
    *   **AI Services (`services.py`)**: The core Machine Learning logic resides here.
        *   **Semantic Search**: Utilizes `SentenceTransformer('all-MiniLM-L6-v2')` to map user queries into vector embeddings, matching them against movie metadata via cosine similarity to provide highly relevant search results even if exact keywords mismatch.
        *   **Recommendation Engine**: Driven by **FAISS** (Facebook AI Similarity Search). The system preloads pre-computed movie embeddings from `data/movie_embeddings.pkl`. When evaluating similar movies, it calculates nearest neighbors and reranks them based on a hybrid formula: `(0.7 * cosine_similarity) + (0.3 * user_rating_score)`. If the vector lookup fails, it falls back to calculating Jaccard similarity across parsed movie metadata and genres.
        *   **Sentiment Analysis**: A rule-based parser automatically evaluates user-submitted reviews to tag them as *Positive*, *Negative*, or *Neutral*.
*   **Data Pipeline (`recommendation/` folder)**: Features offline ETL and data modeling workflows via Jupyter Notebooks (e.g., `recommendation.ipynb`, `data_movies.ipynb`) to clean datasets and pre-generate the vector embeddings used by the backend.

## 3. Database (DB)
The Database uses a customized relational schema (PostgreSQL) split into two distinct structures:

*   **Active Movie Models (`apps/movies/models.py`)**:
    *   `Movie`: Stores details like `tmdb_id`, `description`, `ai_metadata`, `trailer_url`, and `rating`.
    *   `Genre`: Linked to `Movie` via a Many-to-Many relationship table.
    *   `Review`: Tracks user comments, ratings (validated 1-10 constraints), and records the AI-provided `sentiment_label`.
*   **Legacy DB-First Models (`apps/db_models.py`)**: 
    *   Generated dynamically using Django's `inspectdb` (`managed = False`). This connects to vestigial tables (`academics_classroom`, `enrollments_enrollment`, `students_studentprofile`), suggesting the codebase was iterated on top of a previous generic Django boilerplate or shared database instance.

## Summary
The project operates as an **Intelligent Movie Catalog**, successfully merging classical MVC web architecture with modern NLP tools (SentenceTransformers) and vector similarity indexes (FAISS) to deliver a seamless, personalized content discovery experience.
