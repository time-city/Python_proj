from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserInteraction, Review
from .ml_utils import analyze_sentiment


@receiver(post_save, sender=UserInteraction)
def compute_interaction_sentiment(sender, instance, **kwargs):
    if instance.comment and instance.sentiment_score is None:
        result = analyze_sentiment(instance.comment)
        UserInteraction.objects.filter(pk=instance.pk).update(
            sentiment_score=result["score"]
        )


@receiver(post_save, sender=Review)
def compute_review_sentiment(sender, instance, created, **kwargs):
    """Back-fill sentiment_label on legacy Review rows using the RoBERTa pipeline."""
    if not created or not instance.comment or instance.sentiment_label:
        return
    result = analyze_sentiment(instance.comment)
    Review.objects.filter(pk=instance.pk).update(sentiment_label=result["label"])
