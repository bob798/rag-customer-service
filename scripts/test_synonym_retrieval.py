"""
检索质量探索：近义词场景下的检索结果对比（完整 Pipeline 版）

测试维度：
  A. 原始查询 vs QueryRewriter 改写后 → 验证 QueryRewriter 是否有效
  B. normalize vs synonym_expansion 两种 prompt variant → 对比效果
  C. 三种检索方式（向量/BM25/混合）在改写前后的命中率变化

用法：
  # 需要 LLM API Key（QueryRewriter/IntentClassifier 依赖）
  export ANTHROPIC_API_KEY=sk-ant-...
  .venv/bin/python scripts/test_synonym_retrieval.py

  # 无 API Key 时，跳过 QueryRewriter 对比，仅测原始检索
  .venv/bin/python scripts/test_synonym_retrieval.py --no-llm

需要本地已缓存 gte-Qwen2-1.5B 模型（~3.2GB）。
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for noisy in ("chromadb", "jieba", "httpx", "sentence_transformers", "torch",
              "litellm", "httpcore", "LiteLLM"):
    logging.getLogger(noisy).setLevel(logging.CRITICAL)
logging.basicConfig(level=logging.ERROR)

# ---------------------------------------------------------------------------
# 知识库：桌面近场音响系统 FAQ
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

# ---------------------------------------------------------------------------
# 测试查询组
# ---------------------------------------------------------------------------
QUERY_GROUPS = [
    {
        "name": "无声故障",
        "queries": ["音箱没有声音", "音响不出声", "扬声器没声音", "喇叭没响"],
        "expected_chunks": ["a1"],
    },
    {
        "name": "杂音故障",
        "queries": ["音响有杂音", "音箱嗡嗡响", "扬声器有噪音", "喇叭发出嗡嗡声"],
        "expected_chunks": ["a2"],
    },
    {
        "name": "蓝牙连接",
        "queries": ["蓝牙音箱连不上", "音响蓝牙配对失败", "蓝牙扬声器搜不到"],
        "expected_chunks": ["a6"],
    },
    {
        "name": "低音调节",
        "queries": ["音箱低音调节", "音响低频太弱", "扬声器Bass怎么调", "喇叭低音不够"],
        "expected_chunks": ["a7"],
    },
]


async def build_stores(tmp_dir: str):
    from core.knowledge.embedder import GteQwen2Embedder
    from core.knowledge.vector_store import ChromaVectorStore
    from core.knowledge.bm25_store import Bm25Store

    print("⏳ 加载 GTE-Qwen2 embedding 模型（首次约 20-30 秒）...")
    embedder = GteQwen2Embedder()
    vector_store = ChromaVectorStore(
        embedder=embedder,
        collection_name="synonym_test",
        persist_directory=tmp_dir,
    )
    bm25_store = Bm25Store()
    print(f"📚 写入 {len(AUDIO_FAQ)} 条知识库...")
    await vector_store.add(AUDIO_FAQ)
    bm25_store.add(AUDIO_FAQ)
    print("✅ 知识库就绪\n")
    return embedder, vector_store, bm25_store


async def retrieve_raw(query: str, embedder, vector_store, bm25_store, top_k=3):
    """直接检索（不经过 QueryRewriter）"""
    from core.rag.retriever import HybridRetriever
    query_vec = (await embedder.embed([query]))[0]
    retriever = HybridRetriever(vector_store=vector_store, bm25_store=bm25_store)
    vector_r = await vector_store.query(query_vec, top_k=top_k)
    bm25_r = bm25_store.search(query, top_k=top_k)
    hybrid_r = await retriever.retrieve(query_vec, query, top_k=top_k)
    return vector_r, bm25_r, hybrid_r


def top1_hit(results, expected):
    return bool(results) and results[0]["chunk_id"] in expected


def fmt_top3(results, expected):
    lines = []
    for i, r in enumerate(results):
        cid = r["chunk_id"]
        hit = "✅" if cid in expected else "  "
        score = r.get("score", r.get("distance", 0))
        preview = r["content"][:35].replace("\n", " ")
        lines.append(f"    {hit} #{i+1} [{cid}] {score:.4f}  {preview}...")
    return "\n".join(lines) if lines else "    (空)"


async def run_no_llm(embedder, vector_store, bm25_store):
    """无 LLM 模式：仅测原始检索（复现上次实验）"""
    print("=" * 68)
    print("📊 原始检索质量（无 QueryRewriter）")
    print("=" * 68)

    total = hybrid_hits = vec_hits = bm25_hits = 0
    for group in QUERY_GROUPS:
        print(f"\n【{group['name']}】  期望: {group['expected_chunks']}")
        expected = set(group["expected_chunks"])
        for query in group["queries"]:
            total += 1
            vec_r, bm25_r, hybrid_r = await retrieve_raw(
                query, embedder, vector_store, bm25_store
            )
            v = top1_hit(vec_r, expected)
            b = top1_hit(bm25_r, expected)
            h = top1_hit(hybrid_r, expected)
            if v: vec_hits += 1
            if b: bm25_hits += 1
            if h: hybrid_hits += 1
            print(f"  「{query}」  向量{'✅' if v else '❌'}  BM25{'✅' if b else '❌'}  混合{'✅' if h else '❌'}")

    print(f"\n{'='*68}")
    print(f"汇总 (Top-1命中/{total})")
    print(f"  向量: {vec_hits}/{total} ({vec_hits/total:.0%})  "
          f"BM25: {bm25_hits}/{total} ({bm25_hits/total:.0%})  "
          f"混合: {hybrid_hits}/{total} ({hybrid_hits/total:.0%})")
    print("=" * 68)


async def run_with_llm(embedder, vector_store, bm25_store):
    """LLM 模式：对比 normalize vs synonym_expansion 两种改写策略"""
    from core.llm.factory import LLMFactory
    from core.rag.query_rewriter import QueryRewriter

    model = (os.getenv("ANTHROPIC_API_KEY") and "claude-haiku-4-5-20251001") or \
            (os.getenv("OPENAI_API_KEY") and "gpt-4o-mini") or \
            (os.getenv("DEEPSEEK_API_KEY") and "deepseek/deepseek-chat")
    if not model:
        print("⚠️  未检测到 API Key，切换到 --no-llm 模式")
        await run_no_llm(embedder, vector_store, bm25_store)
        return

    print(f"🤖 使用 LLM: {model}")
    llm = LLMFactory(model=model)

    rewriters = {
        "原始（无改写）": None,
        "normalize": QueryRewriter(llm, variant="normalize"),
        "synonym_expansion": QueryRewriter(llm, variant="synonym_expansion"),
    }

    # 统计各策略命中数
    stats: dict[str, dict] = {k: {"vec": 0, "bm25": 0, "hybrid": 0, "total": 0}
                               for k in rewriters}

    print("\n" + "=" * 68)
    print("📊 QueryRewriter 改写效果对比（完整 Pipeline 检索层）")
    print("=" * 68)

    for group in QUERY_GROUPS:
        print(f"\n【{group['name']}】  期望: {group['expected_chunks']}")
        print("-" * 55)
        expected = set(group["expected_chunks"])

        for query in group["queries"]:
            print(f"\n  原始查询: 「{query}」")

            for label, rewriter in rewriters.items():
                stats[label]["total"] += 1

                # 获取改写后的查询
                if rewriter is None:
                    rewritten = query
                else:
                    rewritten = await rewriter.rewrite(query)

                # 执行检索
                vec_r, bm25_r, hybrid_r = await retrieve_raw(
                    rewritten, embedder, vector_store, bm25_store
                )
                v = top1_hit(vec_r, expected)
                b = top1_hit(bm25_r, expected)
                h = top1_hit(hybrid_r, expected)
                if v: stats[label]["vec"] += 1
                if b: stats[label]["bm25"] += 1
                if h: stats[label]["hybrid"] += 1

                rewrite_display = ""
                if rewriter is not None and rewritten != query:
                    rewrite_display = f" → 「{rewritten}」"

                print(f"  [{label}]{rewrite_display}")
                print(f"    向量{'✅' if v else '❌'}  BM25{'✅' if b else '❌'}  混合{'✅' if h else '❌'}")

                # 展开混合检索详情（方便对比）
                if not h:
                    print(fmt_top3(hybrid_r, expected))

    # 汇总
    total = stats["原始（无改写）"]["total"]
    print(f"\n{'='*68}")
    print(f"📈 汇总对比（混合检索 Top-1 命中率，共 {total} 个查询）")
    print(f"{'策略':<20} {'向量':>6} {'BM25':>6} {'混合':>6}")
    print("-" * 42)
    for label, s in stats.items():
        t = s["total"]
        print(f"{label:<20} {s['vec']:>3}/{t} ({s['vec']/t:.0%})  "
              f"{s['bm25']:>3}/{t} ({s['bm25']/t:.0%})  "
              f"{s['hybrid']:>3}/{t} ({s['hybrid']/t:.0%})")
    print("=" * 68)


async def main(no_llm: bool):
    tmp_dir = tempfile.mkdtemp(prefix="rag_synonym_")
    embedder, vector_store, bm25_store = await build_stores(tmp_dir)

    if no_llm:
        await run_no_llm(embedder, vector_store, bm25_store)
    else:
        await run_with_llm(embedder, vector_store, bm25_store)

    print(f"\n临时目录: {tmp_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-llm", action="store_true",
                        help="跳过 QueryRewriter，仅测原始检索")
    args = parser.parse_args()
    asyncio.run(main(args.no_llm))
