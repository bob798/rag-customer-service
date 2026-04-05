"""Shared fixtures for integration tests.

Uses real implementations of chunker, BM25, and parsers.
Embedder uses a deterministic stub (no model file needed).
LLM uses AsyncMock.
"""
import hashlib
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.interfaces.embedder import BaseEmbedder
from core.knowledge.bm25_store import Bm25Store
from core.knowledge.chunker import SemanticChunker


# ---------------------------------------------------------------------------
# Deterministic embedder — no model required
# ---------------------------------------------------------------------------

class DeterministicEmbedder(BaseEmbedder):
    """Produces fixed-length vectors deterministically from text hash."""

    DIM = 64

    async def embed(self, texts: list[str]) -> list[list[float]]:
        result = []
        for text in texts:
            seed = int(hashlib.md5(text.encode()).hexdigest(), 16)
            vec = []
            for i in range(self.DIM):
                seed = (seed * 1664525 + 1013904223) & 0xFFFFFFFF
                vec.append((seed / 0xFFFFFFFF) * 2 - 1)
            norm = sum(x * x for x in vec) ** 0.5 or 1.0
            result.append([x / norm for x in vec])
        return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def real_chunker():
    return SemanticChunker(chunk_size=256, overlap=50)


@pytest.fixture
def real_bm25_store():
    return Bm25Store()


@pytest.fixture
def deterministic_embedder():
    return DeterministicEmbedder()


@pytest.fixture
def sample_faq_file(tmp_path: Path) -> Path:
    content = """问：如何申请退款？
答：您可以在订单页面点击"申请退款"，填写退款原因后提交。我们会在3个工作日内处理。

问：退款多久到账？
答：退款审核通过后，款项将在3-5个工作日内原路退回至您的支付账户。

问：如何查询订单状态？
答：登录账号后，在"我的订单"页面可以查看所有订单的实时状态。

问：商品发货后可以取消订单吗？
答：商品发货后暂不支持取消订单，但您收到后可以申请退货退款。

问：如何联系客服？
答：您可以通过页面右下角的在线客服按钮联系我们，工作时间为周一至周五9:00-18:00。
"""
    faq_file = tmp_path / "faq.txt"
    faq_file.write_text(content, encoding="utf-8")
    return faq_file


@pytest.fixture
def mock_llm_factory():
    llm = MagicMock()
    llm.complete = AsyncMock(return_value="根据资料，退款需要3-5个工作日。")
    llm.complete_stream = AsyncMock()
    return llm
