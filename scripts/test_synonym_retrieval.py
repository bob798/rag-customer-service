"""
检索质量对比实验：BGEReranker × SynonymAugmentor 2×2 矩阵

配置 A：基线        — NoopReranker，无同义词扩展
配置 B：BGEReranker — 开启精排，无同义词扩展
配置 C：SynonymAug — NoopReranker，知识库侧同义词扩展
配置 D：全部开启   — BGEReranker + SynonymAugmentor

用法：
  .venv/bin/python scripts/test_synonym_retrieval.py

需要本地已缓存：
  - gte-Qwen2-1.5B （~3.2GB，embedding）
  - bge-reranker-v2-m3（~2.1GB，reranker）
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for noisy in ("chromadb", "jieba", "httpx", "sentence_transformers",
              "torch", "FlagEmbedding", "transformers"):
    logging.getLogger(noisy).setLevel(logging.CRITICAL)
logging.basicConfig(level=logging.ERROR)

# ---------------------------------------------------------------------------
# 知识库：桌面近场音响系统 FAQ（原版，不含同义词）
# ---------------------------------------------------------------------------
AUDIO_FAQ = [
    {
        "chunk_id": "a1", "doc_id": "audio_faq",
        "content": "Q: 音箱没有声音怎么办？\nA: 请检查：①音箱电源是否打开 ②音频线是否插紧 ③电脑音量是否调到0或静音 ④音箱旋钮是否调到最小。",
        "metadata": {"source_title": "音响常见问题FAQ"}
    },
    {
        "chunk_id": "a2", "doc_id": "audio_faq",
        "content": "Q: 音响有杂音/嗡嗡声怎么处理？\nA: 杂音通常由电源干扰引起。建议：①将音响电源线单独插一个插座 ②远离路由器、电源适配器等干扰源 ③检查音频线是否接触不良。",
        "metadata": {"source_title": "音响常见问题FAQ"}
    },
    {
        "chunk_id": "a3", "doc_id": "audio_faq",
        "content": "Q: 左右扬声器音量不平衡怎么调？\nA: 在系统声音设置中找到平衡选项，将左右声道调为相等。也可通过音箱背面的平衡旋钮（Balance）手动调整。",
        "metadata": {"source_title": "音响常见问题FAQ"}
    },
    {
        "chunk_id": "a4", "doc_id": "audio_faq",
        "content": "Q: 喇叭发出爆音是什么原因？\nA: 爆音（Pop/Click）常见原因：①开关机时音量过大 ②音频信号削波（音量超过额定功率）③音频线接头松动。建议开机前调低音量，关机后再调低。",
        "metadata": {"source_title": "音响常见问题FAQ"}
    },
    {
        "chunk_id": "a5", "doc_id": "audio_faq",
        "content": "Q: 音箱支持几种连接方式？\nA: 本款桌面近场音响支持三种连接：①3.5mm AUX 有线连接 ②USB 音频（免驱动，即插即用）③蓝牙5.0（连接距离10米以内）。",
        "metadata": {"source_title": "音响常见问题FAQ"}
    },
    {
        "chunk_id": "a6", "doc_id": "audio_faq",
        "content": "Q: 蓝牙音箱连接不上手机怎么办？\nA: ①确认音箱处于配对模式（指示灯快闪）②手机蓝牙列表中删除旧的配对记录，重新搜索 ③距离不超过10米，中间无金属遮挡。",
        "metadata": {"source_title": "音响常见问题FAQ"}
    },
    {
        "chunk_id": "a7", "doc_id": "audio_faq",
        "content": "Q: 音响低音太弱/太强如何调节？\nA: 本款音响内置三段EQ（低音/中音/高音旋钮）。低音不足时顺时针旋转Bass旋钮；低音过强时逆时针调低。桌面近场摆放建议低音旋钮置于12点位。",
        "metadata": {"source_title": "音响常见问题FAQ"}
    },
    {
        "chunk_id": "a8", "doc_id": "audio_faq",
        "content": "Q: 保修政策是什么？\nA: 整机保修1年，扬声器单元保修2年。人为损坏（进液、跌落、改装）不在保修范围内。保修期内免费维修，提供上门取件服务。",
        "metadata": {"source_title": "音响常见问题FAQ"}
    },
]

# 音响领域同义词表
AUDIO_SYNONYMS = {
    "音箱":     ["音响", "扬声器", "喇叭"],
    "没有声音": ["不出声", "无声", "没响", "静音"],
    "杂音":     ["噪音", "嗡嗡声", "嗡嗡响"],
    "蓝牙":     ["无线连接", "BT"],
    "低音":     ["低频", "Bass", "重低音"],
    "爆音":     ["噼啪声", "Pop", "Click"],
}

# 测试查询组
QUERY_GROUPS = [
    {
        "name": "无声故障",
        "queries": ["音箱没有声音", "音响不出声", "扬声器没声音", "喇叭没响"],
        "expected": {"a1"},
    },
    {
        "name": "杂音故障",
        "queries": ["音响有杂音", "音箱嗡嗡响", "扬声器有噪音", "喇叭发出嗡嗡声"],
        "expected": {"a2"},
    },
    {
        "name": "蓝牙连接",
        "queries": ["蓝牙音箱连不上", "音响蓝牙配对失败", "蓝牙扬声器搜不到"],
        "expected": {"a6"},
    },
    {
        "name": "低音调节",
        "queries": ["音箱低音调节", "音响低频太弱", "扬声器Bass怎么调", "喇叭低音不够"],
        "expected": {"a7"},
    },
]


async def build_stores(tmp_dir: str, use_augmentor: bool):
    from core.knowledge.embedder import GteQwen2Embedder
    from core.knowledge.vector_store import ChromaVectorStore
    from core.knowledge.bm25_store import Bm25Store

    embedder = GteQwen2Embedder()
    vector_store = ChromaVectorStore(
        embedder=embedder,
        collection_name=f"syn_test_{'aug' if use_augmentor else 'raw'}",
        persist_directory=tmp_dir,
    )
    bm25_store = Bm25Store()

    chunks = AUDIO_FAQ
    if use_augmentor:
        from core.knowledge.synonym_augmentor import SynonymAugmentor
        aug = SynonymAugmentor(AUDIO_SYNONYMS)
        chunks = aug.augment(chunks)

    await vector_store.add(chunks)
    bm25_store.add(chunks)
    return embedder, vector_store, bm25_store


async def run_config(
    label: str,
    embedder,
    vector_store,
    bm25_store,
    use_bge: bool,
    verbose: bool = False,
) -> dict:
    """Run all queries under one configuration. Returns stats dict."""
    from core.rag.retriever import HybridRetriever
    from core.rag.reranker import NoopReranker, BGEReranker

    retriever = HybridRetriever(vector_store=vector_store, bm25_store=bm25_store)
    reranker = BGEReranker() if use_bge else NoopReranker()

    hits = misses = 0
    miss_details = []

    for group in QUERY_GROUPS:
        expected = group["expected"]
        for query in group["queries"]:
            query_vec = (await embedder.embed([query]))[0]
            candidates = await retriever.retrieve(query_vec, query, top_k=20)
            reranked = await reranker.rerank(query, candidates, top_k=5)

            top1_hit = bool(reranked) and reranked[0]["chunk_id"] in expected
            if top1_hit:
                hits += 1
            else:
                misses += 1
                if verbose:
                    top1_id = reranked[0]["chunk_id"] if reranked else "—"
                    miss_details.append(
                        f"  ❌ [{group['name']}] 「{query}」"
                        f" → 实际Top1=[{top1_id}] 期望={expected}"
                    )

    total = hits + misses
    return {
        "label": label,
        "hits": hits,
        "total": total,
        "pct": hits / total if total else 0,
        "miss_details": miss_details,
    }


async def main():
    tmp = tempfile.mkdtemp(prefix="rag_cmp_")

    print("⏳ 加载 GTE-Qwen2 embedding 模型（首次约 20-30 秒）...")
    t0 = time.time()

    # 同时建两套知识库（raw 和 augmented）
    embedder_raw, vs_raw, bm25_raw = await build_stores(tmp + "/raw", use_augmentor=False)
    embedder_aug, vs_aug, bm25_aug = await build_stores(tmp + "/aug", use_augmentor=True)
    print(f"✅ 知识库就绪（{time.time()-t0:.1f}s）\n")

    print("⏳ 加载 BGE-Reranker-v2-m3（~2.1GB，首次约 10-20 秒）...")
    t1 = time.time()

    configs = [
        ("A: 基线 (NoopReranker, 无扩展)",       embedder_raw, vs_raw, bm25_raw, False),
        ("B: BGEReranker (无扩展)",              embedder_raw, vs_raw, bm25_raw, True),
        ("C: SynonymAug (NoopReranker)",         embedder_aug, vs_aug, bm25_aug, False),
        ("D: BGEReranker + SynonymAug",          embedder_aug, vs_aug, bm25_aug, True),
    ]

    results = []
    for label, emb, vs, bm, use_bge in configs:
        if use_bge and not results:
            print(f"  BGEReranker 加载完成（{time.time()-t1:.1f}s）\n")
        r = await run_config(label, emb, vs, bm, use_bge, verbose=True)
        results.append(r)
        print(f"  [{label}] Top-1命中: {r['hits']}/{r['total']} ({r['pct']:.0%})")

    # 横向对比表
    total_q = results[0]["total"]
    print("\n" + "=" * 62)
    print(f"📊 实验结果对比  ({total_q} 个查询，Top-1 命中率)")
    print("=" * 62)
    print(f"{'配置':<35} {'命中':>5} {'命中率':>7}  {'vs 基线':>8}")
    print("-" * 62)
    base_hits = results[0]["hits"]
    for r in results:
        delta = r["hits"] - base_hits
        delta_str = f"+{delta}" if delta > 0 else (f"{delta}" if delta < 0 else "—")
        print(f"  {r['label']:<33} {r['hits']:>3}/{total_q}  {r['pct']:>6.0%}  {delta_str:>8}")
    print("=" * 62)

    # 显示配置 A 的失败 case（基线错误的地方）
    print("\n📋 基线失败 case（配置 A miss）：")
    for d in results[0]["miss_details"]:
        print(d)

    # 对比：D 比 A 多命中了哪些
    a_miss_queries = {d.split("「")[1].split("」")[0] for d in results[0]["miss_details"]}
    d_miss_queries = {d.split("「")[1].split("」")[0] for d in results[3]["miss_details"]}
    newly_hit = a_miss_queries - d_miss_queries
    if newly_hit:
        print(f"\n✅ D（全开）比 A（基线）新增命中的 queries：")
        for q in sorted(newly_hit):
            print(f"  「{q}」")

    still_miss = a_miss_queries & d_miss_queries
    if still_miss:
        print(f"\n⚠️  D（全开）仍未命中（需进一步分析）：")
        for q in sorted(still_miss):
            print(f"  「{q}」")

    print(f"\n临时目录: {tmp}")


if __name__ == "__main__":
    asyncio.run(main())
