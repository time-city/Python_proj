"""Local ML utilities — sentiment analysis via HuggingFace DistilBERT with rule-based fallback."""

_sentiment_pipeline = None
_pipeline_failed = False

def get_sentiment_pipeline():
    global _sentiment_pipeline, _pipeline_failed
    if _pipeline_failed:
        return None
    if _sentiment_pipeline is None:
        try:
            from transformers import pipeline
            print("Đang nạp mô hình Sentiment AI (DistilBERT siêu nhẹ)...")
            # Dùng model nhẹ, tải nhanh, chiếm ít RAM
            _sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model="distilbert-base-uncased-finetuned-sst-2-english",
                truncation=True,
                max_length=512,
            )
            print("Nạp mô hình Sentiment xong!")
        except Exception as e:
            print("Lỗi khi tải mô hình Sentiment:", e)
            _pipeline_failed = True
            return None
    return _sentiment_pipeline


def analyze_sentiment(text):
    if not text or len(text.strip()) < 5:
        return {"label": "Neutral", "score": 0.5}

    pipe = get_sentiment_pipeline()
    if pipe is None:
        return _rule_based_sentiment(text)

    try:
        result = pipe(text[:512])[0]
        label = result["label"]
        confidence = result["score"]

        label_map = {"positive": "Positive", "negative": "Negative", "neutral": "Neutral"}
        normalized_label = label_map.get(label.lower(), "Neutral")

        if normalized_label == "Positive":
            score = 0.5 + 0.5 * confidence
        elif normalized_label == "Negative":
            score = 0.5 - 0.5 * confidence
        else:
            score = 0.5

        return {"label": normalized_label, "score": round(score, 4)}
    except Exception as e:
        print(f"Lỗi khi dự đoán cảm xúc: {e}")
        return _rule_based_sentiment(text)


def _rule_based_sentiment(text):
    text_lower = text.lower()
    pos = ['good', 'great', 'excellent', 'amazing', 'love', 'best', 'masterpiece']
    neg = ['bad', 'terrible', 'awful', 'hate', 'worst', 'boring', 'trash']
    p = sum(1 for w in pos if w in text_lower)
    n = sum(1 for w in neg if w in text_lower)
    if p > n: return {"label": "Positive", "score": 0.7}
    if n > p: return {"label": "Negative", "score": 0.3}
    return {"label": "Neutral", "score": 0.5}