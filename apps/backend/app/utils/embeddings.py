import math
from typing import Iterable

from sklearn.feature_extraction.text import HashingVectorizer


class HashingEmbeddingService:
    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions
        self.vectorizer = HashingVectorizer(
            n_features=dimensions,
            alternate_sign=False,
            norm=None,
            analyzer="char_wb",
            ngram_range=(2, 4),
        )

    def encode(self, texts: Iterable[str]) -> list[list[float]]:
        matrix = self.vectorizer.transform(list(texts)).toarray()
        vectors: list[list[float]] = []
        for row in matrix:
            norm = math.sqrt(float((row * row).sum())) or 1.0
            vectors.append((row / norm).astype(float).tolist())
        return vectors

    @staticmethod
    def cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right:
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
        right_norm = math.sqrt(sum(b * b for b in right)) or 1.0
        return numerator / (left_norm * right_norm)

