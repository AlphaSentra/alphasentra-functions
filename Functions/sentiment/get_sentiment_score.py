"""Financial sentiment scoring utilities.

Uses VADER to classify text as bullish, neutral, or bearish, returning both
a compound polarity score and a derived confidence value.
"""

from typing import Optional

import nltk
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


# Lazily initialized analyzer to avoid repeated NLTK data lookups and object
# construction on every call.
_analyzer: Optional[SentimentIntensityAnalyzer] = None


def _get_analyzer() -> SentimentIntensityAnalyzer:
    """Return a cached VADER analyzer, downloading the lexicon on first use."""
    global _analyzer
    if _analyzer is None:
        try:
            nltk.data.find("sentiment/vader_lexicon.zip")
        except LookupError:
            nltk.download("vader_lexicon", quiet=True)
        _analyzer = SentimentIntensityAnalyzer()
    return _analyzer


def get_sentiment_score(text: str) -> dict:
    """Score a piece of text and classify it as bullish, neutral, or bearish.

    Thresholds are tightened compared to general-purpose sentiment because
    financial commentary tends toward subtle bias rather than extreme polarity.

    Args:
        text: The input text to analyze.

    Returns:
        dict with keys:
            - score: compound polarity score in [-1.0, 1.0]
            - label: one of "bullish", "neutral", "bearish"
            - confidence: absolute score, interpreted as signal strength
    """
    if not text or not isinstance(text, str):
        return {"score": 0.0, "label": "neutral", "confidence": 0.0}

    analyzer = _get_analyzer()
    compound = analyzer.polarity_scores(text)["compound"]

    # These bounds reduce neutral over-classification for lukewarm commentary.
    if compound > 0.1:
        label = "bullish"
    elif compound < -0.1:
        label = "bearish"
    else:
        label = "neutral"

    confidence = abs(compound)

    return {"score": compound, "label": label, "confidence": confidence}
