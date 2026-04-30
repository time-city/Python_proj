# Kiến trúc hệ thống Recommendation

Tài liệu này mô tả **kiến trúc thực tế đã triển khai** của module `apps/movies`. Đọc kèm code để hiểu sâu — file này chỉ là bản đồ dẫn đường.

---

## 1. Tổng quan

Hệ thống là một **hybrid recommender** kết hợp 3 tín hiệu độc lập rồi trộn lại:

| Tín hiệu | Nguồn | Trả lời câu hỏi |
|----------|-------|-----------------|
| **Content-based** (FAISS + embeddings) | `Movie.description`, `Movie.ai_metadata` | "Phim này giống phim nào về nội dung?" |
| **Collaborative filtering** (TruncatedSVD) | `UserInteraction.rating / sentiment / watch_time` | "Những user có gu giống bạn thích phim nào?" |
| **Sentiment-adjusted rating** (RoBERTa) | `Movie.sentiment_score` × `Movie.rating` | "Phim được đánh giá cao và có vibe phù hợp?" |

Cộng thêm:
- **Recency boost** (additive nhỏ) — phim mới được nhúc nhẹ lên
- **Diversity re-ranking** — tránh top-N toàn 1 thể loại
- **Cold-start staging** — fallback từ pure content → hybrid khi user tích lũy đủ data

---

## 2. Sơ đồ data flow

### 2.1. Khi user xem trang phim → request gợi ý

```
[Browser]
   │  GET /movies/<slug>/   (HTML view)
   │  hoặc GraphQL: movie(slug) { recommendations { ... } }
   ↓
[views.py / schema.py]
   │  user_id = request.user.id (nếu authenticated)
   ↓
[services.py :: get_recommendations(movie_id, user_id, top_n)]
   │
   │  ┌─────────────────────────────────────┐
   │  │ Cold-start router (theo data user)  │
   │  └─────────────────────────────────────┘
   │
   ├─ user_id=None (anonymous)         → _content_only_recommendations()
   ├─ interactions=0  (user mới toanh) → _content_only_recommendations()
   ├─ interactions<5  (data ít)         → get_hybrid_recommendations(user_id=None)
   └─ interactions≥5                    → get_hybrid_recommendations(user_id=X)  ← FULL HYBRID
            │
            ↓
   ┌─────────────────────────────────────────────────┐
   │  Tổng hợp 3 nguồn điểm                          │
   │                                                 │
   │  α·CF + β·content + γ·sentiment_rating + 0.05·recency  │
   │                                                 │
   │  ALPHA=0.50, BETA=0.35, GAMMA=0.15              │
   └─────────────────────────────────────────────────┘
            │
            ↓
   [Diversity re-rank: tránh trùng genre]
            │
            ↓
   Trả về list[Movie] (top_n)
```

### 2.2. Khi user post comment / rating

```
[Browser]
   │  POST review form  hoặc  GraphQL createReview / recordInteraction
   ↓
[views.py :: add_review / schema.py :: CreateReview / RecordInteraction]
   │
   ├─ Tạo Review (legacy, anonymous-friendly)
   └─ Tạo / update UserInteraction (chỉ khi authenticated)
            │
            ↓ (signal post_save)
   [signals.py :: compute_interaction_sentiment]
            │
            ↓
   [ml_utils.py :: analyze_sentiment(comment)]   ← RoBERTa
            │
            ↓
   UPDATE user_interactions SET sentiment_score = ... WHERE pk = ...
```

### 2.3. Maintenance (chạy bằng tay / cron)

```
python manage.py compute_sentiment   → chấm Movie.sentiment_score từ description (1 lần / khi import phim mới)
python manage.py build_cf            → train SVD factors từ user_interactions (định kỳ, sau khi có data)
python manage.py generate_embeddings → tạo lại data/movie_embeddings.pkl (khi import phim mới)
```

---

## 3. Data schema

| Bảng | Vai trò trong recommender |
|------|---------------------------|
| `genres` | Dùng cho diversity re-rank và filter |
| `movies` | Catalog. Cột `sentiment_score` (FloatField, 0-1) là vibe của phim |
| `reviews` | Comment ẩn danh — không tham gia CF, chỉ hiển thị UI và lưu `sentiment_label` |
| `user_interactions` | **Trái tim của CF.** Cặp (user, movie) duy nhất; chứa rating, comment, sentiment_score, watched, watch_time_pct |
| `accounts_user` | Bên `apps.accounts`. CF group user theo gu thông qua FK này |

Quan trọng:
- `Movie.sentiment_score` chấm từ **`description`** (vibe phim). Tính 1 lần.
- `UserInteraction.sentiment_score` chấm từ **comment user**. Mỗi cặp (user, movie) có 1 giá trị riêng.
- 2 cột này ĐỘC LẬP, không ghi đè nhau.

---

## 4. Module map

```
apps/movies/
├── models.py            ← Schema (Genre, Movie, Review, UserInteraction)
├── services.py          ← ★ Bộ não. Mọi logic gợi ý ở đây
├── ml_utils.py          ← RoBERTa sentiment pipeline (lazy-load + fallback)
├── signals.py           ← Auto-chấm sentiment khi user post comment
├── views.py             ← HTML endpoints (home, movie_detail, add_review, upload_movie)
├── schema.py            ← GraphQL (graphene-django) — Query, Mutation, Type
├── apps.py              ← AppConfig.ready() → đăng ký signals
├── admin.py             ← Django admin UI (đã expose sentiment_score)
├── forms.py             ← MovieForm (upload phim)
├── urls.py              ← Routing
└── management/commands/
    ├── compute_sentiment.py    ← Chấm Movie.sentiment_score
    ├── build_cf.py             ← Train CF factors
    ├── generate_embeddings.py  ← Build FAISS index
    ├── import_movies_csv.py    ← Seed catalog
    └── seed_movies.py          ← Seed nhanh
```

Nguyên tắc:
- `services.py` không bao giờ gọi Django views/forms — pure logic.
- `views.py` / `schema.py` là **adapter** — convert request → service call → response.
- `signals.py` chỉ phản ứng với `post_save`, không chứa logic kinh doanh.

---

## 5. Module chi tiết

### 5.1. `services.py` — bộ não

#### 5.1.1. Caching globals

```python
_semantic_model     # SentenceTransformer (all-MiniLM-L6-v2)
_movie_embeddings   # numpy array, shape (n_movies, 384)
_movie_ids          # list[int] — index → movie_id
_faiss_index        # faiss.IndexFlatIP (cosine via inner product trên L2-normalized)
_max_rating         # float

_user_factors       # CF: numpy (n_users, 50)
_item_factors       # CF: numpy (n_movies, 50)
_cf_user_index      # dict user_id → row index
_cf_item_index      # dict movie_id → col index
```

Tất cả load lazy lần đầu được gọi. **Mỗi process Gunicorn worker giữ bản sao riêng** — restart server = mất, gọi lại sẽ load lại.

#### 5.1.2. Hàm public (caller dùng)

| Hàm | Vai trò |
|-----|---------|
| `get_recommendations(movie_id, user_id, top_n)` | **Entry point.** Cold-start staging, route sang content-only hoặc hybrid |
| `get_hybrid_recommendations(movie_id, user_id, top_n)` | Tổng hợp 3 nguồn điểm + diversity re-rank |
| `get_collaborative_recommendations(user_id, top_k)` | Pure CF — trả về list movie_id, dùng nội bộ |
| `build_cf_model()` | Train SVD từ `user_interactions`, populate globals CF |
| `semantic_search(query, top_k)` | Search box: keyword OR semantic, trả về QuerySet |
| `analyze_sentiment(text)` | Re-export từ `ml_utils` (giữ backward compat) |

#### 5.1.3. Hàm internal

| Hàm | Vai trò |
|-----|---------|
| `_content_scores_for(movie_id, top_n)` | FAISS lookup — trả về `{movie_id: cosine_sim}` |
| `_content_only_recommendations(movie_id, top_n)` | Đường legacy: `0.7·cos + 0.3·rating`, fallback genre+Jaccard |
| `get_semantic_model()` | Lazy-load SentenceTransformer |
| `load_embeddings()` | Lazy-load `data/movie_embeddings.pkl` + build FAISS index |
| `calculate_similarity(t1, t2)` | Jaccard (dùng cho fallback khi FAISS miss) |

#### 5.1.4. Công thức trộn (`get_hybrid_recommendations`)

```python
ALPHA, BETA, GAMMA = 0.50, 0.35, 0.15

content_scores = _content_scores_for(seed_movie_id, top_n)
cf_scores      = rank-normalized list từ get_collaborative_recommendations(user_id)

cho mỗi candidate movie:
    c   = content_scores.get(mid, 0.0)
    cf  = cf_scores.get(mid, 0.0)
    s   = (rating/10) * (0.5 + sentiment_score)        # boost positive vibe
    rec = max(0, 1 - age_years/30)                     # phim ≥30 năm: 0

    final = ALPHA·cf + BETA·c + GAMMA·s + 0.05·rec
```

Pool ứng viên = `set(content_scores) ∪ set(cf_scores)`. Không có ứng viên nào → fallback `Movie.objects.order_by('-rating')[:top_n]`.

#### 5.1.5. Diversity re-rank

Sau khi sort theo `final` desc:
1. Đi từ trên xuống, ứng viên nào có genre **chưa xuất hiện** → đẩy vào `diverse[]`
2. Còn lại → `remainder[]`
3. Khi `len(diverse) >= top_n` thì dừng
4. Nếu `diverse` chưa đủ top_n, lấp từ `remainder`

→ Đảm bảo top-N có nhiều genre, không bị 5 phim cùng "Action" liên tiếp.

### 5.2. `ml_utils.py` — sentiment

#### Pipeline

1. Lazy-load `cardiffnlp/twitter-roberta-base-sentiment-latest` (HuggingFace, ~500MB, cache trong `~/.cache/huggingface/`)
2. Truncate text về 512 token
3. Model trả `{label: positive|negative|neutral, score: confidence_0_1}`
4. Convert thành **single 0-1 score**:
   - Positive: `0.5 + 0.5·confidence` → [0.5, 1.0]
   - Negative: `0.5 - 0.5·confidence` → [0.0, 0.5]
   - Neutral: hardcode `0.5`
5. Edge case: text rỗng / <5 ký tự → `0.5`
6. Pipeline load fail → fallback sang `_rule_based_sentiment` (đếm từ pos/neg)

#### Tại sao convert 3 nhãn → 1 số?

Để có thể **so sánh và xếp hạng** trong công thức trộn. Single-axis dễ dùng trong `s_score = rating × (0.5 + sentiment)`.

### 5.3. `signals.py` — auto-sentiment cho comment

2 receiver:
- `post_save(UserInteraction)`: nếu có `comment` và chưa có `sentiment_score` → chấm và update.
- `post_save(Review)`: chỉ chạy khi `created=True` và chưa có `sentiment_label` → chấm và update.

Dùng `.update(...)` thay vì `.save(...)` để **không trigger lại signal** (tránh recursion).

### 5.4. `views.py` / `schema.py` — adapter layer

Cả 2 đều dùng cùng 1 service. Chỉ khác I/O:
- `views.py`: render HTML, đọc form POST data, redirect.
- `schema.py`: graphene Type/Query/Mutation, trả JSON GraphQL.

Authentication được lấy qua `request.user` (HTML) hoặc `info.context.user` (GraphQL). Cả 2 đều convert sang `user_id` rồi pass vào `get_recommendations`.

GraphQL có 2 mutation tách biệt:
- `createReview` — tạo cả `Review` + `UserInteraction` (thân thiện anonymous)
- `recordInteraction` — chỉ tạo/update `UserInteraction` (yêu cầu authenticated, dùng cho rating thầm lặng / watch progress)

---

## 6. Cold-start strategy

| Tình huống | Hành vi |
|------------|---------|
| `user_id=None` | Pure content-based. Identical với hành vi cũ trước upgrade |
| Authenticated, `interactions=0` | Có `movie_id` → content-based; không có → top-rated |
| Authenticated, `interactions<5` | Hybrid nhưng `user_id=None` truyền vào → CF score=0, chỉ content+sentiment+recency |
| Authenticated, `interactions≥5` | Full hybrid (CF + content + sentiment + recency) |

Threshold `5` là tham số mềm — chỉnh trong `services.py:get_recommendations`.

---

## 7. Lifecycle của `Movie.sentiment_score`

```
[Movie được import]
   │
   │  Movie.sentiment_score = NULL
   ↓
[python manage.py compute_sentiment]
   │
   │  for movie where sentiment_score IS NULL:
   │      score = analyze_sentiment(movie.description)
   │      UPDATE
   ↓
[Movie.sentiment_score = float ∈ [0, 1]]
   │
   │  Đứng yên vĩnh viễn (trừ khi gọi --all)
   ↓
[get_hybrid_recommendations đọc tại runtime]
```

**Hạn chế đã biết:** chấm trên description nên phim drama nặng (Schindler's List) sẽ có score thấp dù là kiệt tác. Hướng nâng cấp tương lai: aggregate `AVG(user_interactions.sentiment_score)` về `movies.sentiment_score` khi đã có ≥N comment.

---

## 8. Lifecycle của CF model

```
[user_interactions trống]
   │
   │  build_cf_model() trả về sớm, _user_factors=None
   ↓
[Có ≥50 user × ≥5 ratings (rule of thumb)]
   │
   ↓
[python manage.py build_cf]
   │
   │  Đọc tất cả user_interactions
   │  Build sparse matrix shape (n_users, n_movies)
   │  TruncatedSVD(n_components=min(50, ...))
   │  → _user_factors, _item_factors trong RAM
   ↓
[get_collaborative_recommendations dùng được]
   │
   │  user_vec = _user_factors[u_idx]
   │  scores   = _item_factors @ user_vec
   │  top-K argsort
   ↓
[Trả về list[movie_id] rank theo predicted preference]
```

**Lưu ý production:**
1. Mỗi worker Gunicorn giữ factors riêng → cần train cho từng worker, hoặc pickle ra Redis/disk.
2. Restart = factors mất → request đầu tiên fallback sang content-only cho đến khi `build_cf_model()` được gọi lại.
3. Train định kỳ (nightly cron) — gu user thay đổi chậm, không cần real-time.

---

## 9. Công thức điểm mỗi tín hiệu

### Content score
- FAISS cosine similarity giữa embedding của seed movie và mỗi candidate.
- Embedding sinh từ `f"{title}. {description} {ai_metadata}"` qua `all-MiniLM-L6-v2` (384-dim).
- Range: [-1, 1] nhưng thực tế ~[0, 1] sau khi L2-normalize.

### CF score
- `_item_factors @ user_vector` — dot product 50-dim.
- Range: không bound. Code rank-normalize về [0, 1] trước khi trộn:
  ```python
  cf_scores[mid] = 1.0 - rank / len(cf_ids)
  ```

### Sentiment-adjusted rating
- `s_score = (rating/10) × (0.5 + sentiment_score)`
- Phim rating=10, sentiment=1.0 → `1.0 × 1.5 = 1.5`
- Phim rating=10, sentiment=0.0 → `1.0 × 0.5 = 0.5`
- Phim rating=5,  sentiment=0.5 → `0.5 × 1.0 = 0.5`

### Recency
- `recency = max(0, 1 - age_years/30)` — phim năm nay = 1.0, phim ≥30 năm = 0.0.
- Multiplier nhỏ (0.05) — chỉ là nudge, không quyết định.

---

## 10. Search subsystem (`semantic_search`)

Ngoài luồng recommend chính. Dùng cho ô search trên home page.

```python
def semantic_search(query, top_k):
    # 1. Keyword pass: ICONTAINS trên title, description, ai_metadata
    keyword_qs = Movie.objects.filter(Q(title__icontains=q) | ...)

    # 2. Semantic pass: encode query → cosine_distance vs all embeddings → top_k
    query_emb = SentenceTransformer.encode([query])
    distances = cdist(query_emb, embeddings, 'cosine')
    semantic_ids = argsort(distances)[:top_k]

    # 3. Merge: keyword trước (đảm bảo relevance literal), semantic sau (deduplicated)
    return Movie.objects.filter(id__in=merged_ids).order_by(preserved_order)
```

Mục đích: cho phép cả truy vấn literal ("Inception") lẫn vibe ("dreamlike thriller about heists").

---

## 11. Tham số tunable

| Tham số | File | Giá trị mặc định | Khi nào điều chỉnh |
|---------|------|------------------|---------------------|
| `ALPHA / BETA / GAMMA` | `services.py:get_hybrid_recommendations` | 0.50 / 0.35 / 0.15 | Khi A/B test cho thấy 1 tín hiệu áp đảo / yếu |
| Cold-start threshold | `services.py:get_recommendations` | `5` interactions | Khi đo offline thấy CF cần nhiều/ít data hơn |
| `n_components` SVD | `services.py:build_cf_model` | 50 | Tăng khi catalog/user lớn (>10k user) |
| Recency window | `services.py:get_hybrid_recommendations` | 30 năm | Theo target audience |
| `top_n * 4` candidate pool | nhiều chỗ | 4× | Tăng nếu diversity re-rank cắt mất quá nhiều |
| Sentiment confidence threshold | (không có) | — | Có thể thêm: bỏ qua kết quả `score < 0.6` |

---

## 12. Cách operator chạy hệ thống

### Lần đầu (sau khi DB có schema mới)

```bash
pip install -r requirements.txt
python manage.py compute_sentiment        # chấm vibe cho mọi phim, ~5-15 phút
python manage.py generate_embeddings      # build FAISS index, nếu chưa có
python manage.py runserver
```

### Định kỳ

```bash
# Nightly (cron)
python manage.py build_cf                 # train CF model

# Khi import phim mới
python manage.py compute_sentiment        # chỉ chấm phim chưa có score
python manage.py generate_embeddings      # rebuild index
```

### Verify

```sql
-- Sentiment đã chấm hết chưa
SELECT COUNT(*) total, COUNT(sentiment_score) scored FROM movies;

-- Có user nào tương tác chưa
SELECT COUNT(DISTINCT user_id), COUNT(*) FROM user_interactions;

-- Phân bố sentiment
SELECT
  CASE
    WHEN sentiment_score < 0.3 THEN 'Negative'
    WHEN sentiment_score > 0.7 THEN 'Positive'
    ELSE 'Neutral'
  END bucket, COUNT(*)
FROM movies GROUP BY bucket;
```

---

## 13. Trade-offs & known limitations

| Vấn đề | Hiện trạng | Hướng xử lý |
|--------|-----------|-------------|
| `Movie.sentiment_score` từ description, không phản ánh dư luận | Chấp nhận làm fallback nền | Khi đủ comment, switch sang `AVG(user_interactions.sentiment_score)` |
| CF factors trong RAM, không persist | Mỗi worker train riêng, restart = mất | Pickle ra Redis/disk khi scale ra nhiều worker |
| `Movie.objects.get(id=mid)` trong loop hybrid | N+1 queries với top_n lớn | Bulk fetch `Movie.objects.filter(id__in=all_ids).select_related/prefetch_related` |
| Cold-start threshold = 5 cứng | Chưa tune theo data thật | A/B test khi có ≥1k user |
| RoBERTa load lần đầu chậm + tốn RAM | ~500MB / 1GB peak | Pre-bake vào image production |
| Diversity re-rank chỉ check genre overlap | Có thể cắt mất phim hay | Cân nhắc MMR (maximal marginal relevance) thay vì hard exclude |

---

## 14. Glossary

| Thuật ngữ | Nghĩa |
|-----------|-------|
| **Embedding** | Vector số biểu diễn ý nghĩa của text. Cosine similarity giữa 2 embedding ≈ độ giống nhau. |
| **FAISS** | Thư viện C++ của Meta cho vector search. `IndexFlatIP` = inner product (cosine sau khi L2-normalize). |
| **TruncatedSVD** | Phân rã ma trận thưa thớt thành 2 ma trận factor nhỏ. Cốt lõi của matrix factorization. |
| **Cold-start** | Tình huống không có data (user mới, phim mới) — recommender phải có chiến lược fallback. |
| **Hybrid recommender** | Trộn nhiều phương pháp (CB + CF + ...) để vá điểm yếu của từng cái. |
| **Content-based filtering (CB)** | Gợi ý dựa trên đặc tính nội dung của item. |
| **Collaborative filtering (CF)** | Gợi ý dựa trên hành vi của tập user, không cần hiểu nội dung item. |

---

## 15. Đọc tiếp

Để đi sâu hơn:

1. **Mathematical foundation**: search "matrix factorization for recommendation" — paper Koren 2009 "Matrix Factorization Techniques for Recommender Systems" là kinh điển.
2. **Sentence embeddings**: tài liệu của `sentence-transformers` về `all-MiniLM-L6-v2`.
3. **HuggingFace pipeline**: `transformers` docs cho `pipeline("sentiment-analysis")`.
4. **FAISS internals**: tutorial trên github của facebookresearch/faiss.
