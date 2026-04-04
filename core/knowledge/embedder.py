import asyncio
import logging
from core.interfaces import BaseEmbedder

logger = logging.getLogger(__name__)


class GteQwen2Embedder(BaseEmbedder):
    """Embedding model using gte-Qwen2-1.5B-instruct (local, Chinese MTEB ~70).

    The underlying SentenceTransformer.encode() is synchronous and CPU/GPU bound.
    It is run in a thread pool via run_in_executor to avoid blocking the event loop.
    """

    def __init__(self, model_name: str = "Alibaba-NLP/gte-Qwen2-1.5B-instruct"):
        self.model_name = model_name
        self._model = None  # lazy load

    def _load_model(self):
        """Lazy load the model on first use."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def _encode_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous encoding (runs in thread pool)."""
        model = self._load_model()
        embeddings = model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts asynchronously using thread pool executor."""
        if not texts:
            return []
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._encode_sync, texts)
