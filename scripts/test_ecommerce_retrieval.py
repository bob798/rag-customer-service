"""
检索质量对比实验：BGEReranker × SynonymAugmentor 2×2 矩阵（电商客服场景）

配置 A：基线        — NoopReranker，无同义词扩展
配置 B：BGEReranker — 开启精排，无同义词扩展
配置 C：SynonymAug — NoopReranker，知识库侧同义词扩展
配置 D：全部开启   — BGEReranker + SynonymAugmentor

用法：
  .venv/bin/python scripts/test_ecommerce_retrieval.py

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
# 知识库：电商客服 FAQ
# ---------------------------------------------------------------------------
ECOMMERCE_FAQ = [
    {
        "chunk_id": "e1", "doc_id": "ecommerce_faq",
        "content": "Q: 如何申请退款？\nA: 登录账号后进入「我的订单」，找到对应订单点击「申请退款」，填写退款原因后提交。退款审核通常1个工作日内完成，款项原路返回需3-5个工作日。",
        "metadata": {"source_title": "电商客服FAQ"}
    },
    {
        "chunk_id": "e2", "doc_id": "ecommerce_faq",
        "content": "Q: 退款多久到账？\nA: 审核通过后，退款将在3-5个工作日内原路返回至您的支付账户。银行卡退款可能需要额外1-3个工作日处理时间，具体以银行到账通知为准。",
        "metadata": {"source_title": "电商客服FAQ"}
    },
    {
        "chunk_id": "e3", "doc_id": "ecommerce_faq",
        "content": "Q: 如何查询订单状态？\nA: 可通过以下方式查询：①登录APP进入「我的订单」②打开小程序点击「订单查询」③拨打客服热线400-xxx-xxxx报订单号查询。",
        "metadata": {"source_title": "电商客服FAQ"}
    },
    {
        "chunk_id": "e4", "doc_id": "ecommerce_faq",
        "content": "Q: 发货需要多长时间？\nA: 普通商品下单后48小时内发货；预售商品以商品页面标注时间为准；节假日期间发货时间顺延1-2天。付款后可在订单详情查看预计发货时间。",
        "metadata": {"source_title": "电商客服FAQ"}
    },
    {
        "chunk_id": "e5", "doc_id": "ecommerce_faq",
        "content": "Q: 如何修改收货地址？\nA: 订单未发货前可修改地址：进入「我的订单」→「订单详情」→「修改地址」。发货后无法修改，可联系快递公司申请转寄服务。",
        "metadata": {"source_title": "电商客服FAQ"}
    },
    {
        "chunk_id": "e6", "doc_id": "ecommerce_faq",
        "content": "Q: 如何申请换货？\nA: 收到商品后7天内可申请换货：①确保商品未使用且包装完整②进入订单页面选择「申请售后」→「换货」③填写换货原因并上传照片。换货运费由平台承担。",
        "metadata": {"source_title": "电商客服FAQ"}
    },
    {
        "chunk_id": "e7", "doc_id": "ecommerce_faq",
        "content": "Q: 积分如何使用？\nA: 积分可在结算页面抵扣现金，100积分=1元。每笔订单最多使用积分抵扣金额的30%。积分有效期为获得后1年，过期自动清零。",
        "metadata": {"source_title": "电商客服FAQ"}
    },
    {
        "chunk_id": "e8", "doc_id": "ecommerce_faq",
        "content": "Q: 忘记密码怎么办？\nA: 点击登录页「忘记密码」，通过手机验证码或邮箱验证重置密码。若手机号已更换，请联系客服提供身份信息后人工处理，通常1个工作日内完成。",
        "metadata": {"source_title": "电商客服FAQ"}
    },
    {
        "chunk_id": "e9", "doc_id": "ecommerce_faq",
        "content": "Q: 物流信息多久更新？\nA: 快递揽件后通常4-6小时更新物流信息。如超过24小时无更新，可在订单页面点击「催促发货」或直接联系快递公司（单号可在订单详情查看）。",
        "metadata": {"source_title": "电商客服FAQ"}
    },
    {
        "chunk_id": "e10", "doc_id": "ecommerce_faq",
        "content": "Q: 收到商品有质量问题怎么办？\nA: 请在收货后48小时内拍照记录问题并联系客服。平台提供：①免费退换货②补发商品③退款补偿三种解决方案，客服会根据实际情况为您处理。",
        "metadata": {"source_title": "电商客服FAQ"}
    },
]

# 电商领域同义词表
ECOMMERCE_SYNONYMS = {
    "退款":   ["退货", "退钱", "退费", "申请退款", "返款"],
    "订单":   ["购买记录", "交易记录", "买的东西", "下单记录"],
    "发货":   ["出库", "配送", "发出", "寄出", "出货"],
    "物流":   ["快递", "运输", "配送情况", "快递信息"],
    "换货":   ["更换商品", "调换", "换一个", "重新发货"],
    "积分":   ["点数", "优惠点", "会员积分"],
    "密码":   ["登录密码", "账号密码", "忘记密码", "密码重置"],
    "质量问题": ["商品有问题", "坏了", "损坏", "残次品", "瑕疵"],
}

# 测试查询组
QUERY_GROUPS = [
    {
        "name": "退款流程",
        "queries": ["如何申请退款", "怎么退货", "退钱流程", "申请退费步骤"],
        "expected": {"e1"},
    },
    {
        "name": "退款到账",
        "queries": ["退款多久到账", "退钱要几天", "退费到账时间", "退款什么时候返回"],
        "expected": {"e2"},
    },
    {
        "name": "订单查询",
        "queries": ["如何查询订单", "查看购买记录", "订单状态怎么看", "查交易记录"],
        "expected": {"e3"},
    },
    {
        "name": "发货时效",
        "queries": ["发货需要多久", "几天出库", "什么时候配送", "多久寄出"],
        "expected": {"e4"},
    },
    {
        "name": "换货申请",
        "queries": ["如何申请换货", "怎么更换商品", "想换一个", "调换商品流程"],
        "expected": {"e6"},
    },
]


async def build_stores(tmp_dir: str, use_augmentor: bool):
    from core.knowledge.embedder import GteQwen2Embedder
    from core.knowledge.vector_store import ChromaVectorStore
    from core.knowledge.bm25_store import Bm25Store

    embedder = GteQwen2Embedder()
    vector_store = ChromaVectorStore(
        embedder=embedder,
        collection_name=f"ec_test_{'aug' if use_augmentor else 'raw'}",
        persist_directory=tmp_dir,
    )
    bm25_store = Bm25Store()

    chunks = ECOMMERCE_FAQ
    if use_augmentor:
        from core.knowledge.synonym_augmentor import SynonymAugmentor
        aug = SynonymAugmentor(ECOMMERCE_SYNONYMS)
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
    tmp = tempfile.mkdtemp(prefix="rag_ec_")

    print("⏳ 加载 GTE-Qwen2 embedding 模型（首次约 20-30 秒）...")
    t0 = time.time()

    embedder_raw, vs_raw, bm25_raw = await build_stores(tmp + "/raw", use_augmentor=False)
    embedder_aug, vs_aug, bm25_aug = await build_stores(tmp + "/aug", use_augmentor=True)
    print(f"✅ 知识库就绪（{time.time()-t0:.1f}s）\n")

    print("⏳ 加载 BGE-Reranker-v2-m3（~2.1GB，首次约 10-20 秒）...")
    t1 = time.time()

    configs = [
        ("A: 基线 (NoopReranker, 无扩展)",   embedder_raw, vs_raw, bm25_raw, False),
        ("B: BGEReranker (无扩展)",          embedder_raw, vs_raw, bm25_raw, True),
        ("C: SynonymAug (NoopReranker)",     embedder_aug, vs_aug, bm25_aug, False),
        ("D: BGEReranker + SynonymAug",      embedder_aug, vs_aug, bm25_aug, True),
    ]

    results = []
    for label, emb, vs, bm, use_bge in configs:
        if use_bge and not results:
            print(f"  BGEReranker 加载完成（{time.time()-t1:.1f}s）\n")
        r = await run_config(label, emb, vs, bm, use_bge, verbose=True)
        results.append(r)
        print(f"  [{label}] Top-1命中: {r['hits']}/{r['total']} ({r['pct']:.0%})")

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

    print("\n📋 基线失败 case（配置 A miss）：")
    for d in results[0]["miss_details"]:
        print(d)

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
