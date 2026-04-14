# 混合检索评测分析报告

> 日期: 2026-04-10 | 数据源: paddleocr_raw_markdown.md (19 chunks, 25 QA)

## 评测结果

### Round 2（25 题，含 15 个复杂场景）

| 指标 | BM25-only | Vector-only | Hybrid (RRF) |
|---|---|---|---|
| Hit@1 | 14/23 (61%) | 19/23 (83%) | 19/23 (83%) |
| Hit@3 | 20/23 (87%) | 21/23 (91%) | 21/23 (91%) |
| MRR | 0.733 | 0.862 | 0.871 |

### Round 1 对比（原始 10 题）

| 指标 | BM25 R1→R2 | Vector R1→R2 | Hybrid R1→R2 |
|---|---|---|---|
| Hit@1 | 11% → 61% | 78% → 83% | 78% → 83% |
| Hit@3 | 78% → 87% | 89% → 91% | 89% → 91% |
| MRR | 0.430 → 0.733 | 0.833 → 0.862 | 0.833 → 0.871 |

> 注：BM25 大幅提升是因为新增 case 含更多精确关键词（THD、ACP、100台等），BM25 擅长精确匹配。

## 逐题分析（25 题）

### 原始 10 题（amp-001 ~ amp-010）

| ID | 问题 | BM25 | Vector | Hybrid | 诊断 |
|---|---|---|---|---|---|
| amp-001 | 输出功率？ | rr=0.2 | **Hit@1** | Hit@2 ⚠️ | Hybrid 退步：BM25 把测试条件推到 Top-1 |
| amp-002 | 连接蓝牙？ | Hit@2 | **Hit@1** | **Hit@1** | OK |
| amp-003 | 电压供电？ | Hit@2 | **Hit@1** | **Hit@1** | OK |
| amp-004 | 有线输入？ | **Hit@1** | Hit@2 | **Hit@1** | Hybrid 互补成功 |
| amp-005 | 什么芯片？ | Hit@3 | **Hit@1** | **Hit@1** | OK |
| amp-006 | 蓝牙版本？ | Hit@3 | **Hit@1** | **Hit@1** | OK |
| amp-007 | 扬声器接线？ | Hit@2 | **Hit@1** | **Hit@1** | OK |
| **amp-008** | **认证？** | **Miss** | **Miss** | **Miss** | 全 Miss — FCC chunk 语义距离远 |
| amp-009 | 电源开关？ | Hit@2 | **Hit@1** | **Hit@1** | OK |
| amp-010 | 恢复出厂？ | N/A | N/A | N/A | out-of-scope 测试 |

### 新增 15 题（amp-011 ~ amp-025）

| ID | 问题 | 类别 | BM25 | Vector | Hybrid | 诊断 |
|---|---|---|---|---|---|---|
| amp-011 | 蓝牙有线同时连哪个优先？ | multi-hop | **Hit@1** | **Hit@1** | **Hit@1** | 三方全命中 |
| amp-012 | 能直接带耳机吗？ | negation | **Hit@1** | **Hit@1** | **Hit@1** | 否定信息检索成功 |
| amp-013 | 信噪比是多少？ | table | Miss | **Hit@1** | Hit@2 ⚠️ | BM25 失败（SNR 在 HTML 表格中），Hybrid 退步 |
| amp-014 | 产品尺寸多大？ | specs | **Hit@1** | Hit@2 | **Hit@1** | BM25 互补成功 |
| amp-015 | 保修期多长？ | policy | **Hit@1** | **Hit@1** | **Hit@1** | OK |
| amp-016 | 怎么用电脑调音？ | usage-complex | **Hit@1** | **Hit@1** | **Hit@1** | OK |
| amp-017 | 最低负载阻抗？ | table | **Hit@1** | **Hit@1** | **Hit@1** | 表格数据两方都能命中 |
| amp-018 | 蓝牙播放最大功率？ | reasoning | **Hit@1** | **Hit@1** | **Hit@1** | 多信息融合成功 |
| amp-019 | 支持 USB-C 供电吗？ | synonym | **Hit@1** | **Hit@1** | **Hit@1** | 同义词匹配成功（USB-C → USB Type-C） |
| amp-020 | 干扰收音机怎么办？ | troubleshoot | **Hit@1** | **Hit@1** | **Hit@1** | FCC 段落能检索到（但 amp-008"认证"不行） |
| amp-021 | 批量采购优惠？ | commercial | **Hit@1** | **Hit@1** | **Hit@1** | OK |
| amp-022 | THD+N 失真率？ | table | **Hit@1** | **Hit@1** | **Hit@1** | OK |
| amp-023 | 工作温度范围？ | specs-implicit | **Hit@1** | **Hit@1** | **Hit@1** | 隐含参数也能命中 |
| **amp-024** | **保存调音设置不丢失？** | usage-complex | **Hit@1** | **Miss** | **Miss** | Vector/Hybrid 失败，BM25 靠"保存"关键词命中 |
| amp-025 | 和 JBL 比？ | out-of-scope | N/A | N/A | N/A | out-of-scope 测试 |

## 核心发现

### 1. Hybrid MRR 首次超过 Vector（0.871 > 0.862）
扩大 case 后 Hybrid 终于体现出融合价值。BM25 在 amp-004（有线输入）、amp-014（尺寸）上互补了 Vector 的不足。

### 2. 失败 case 分析（4 题 Miss）

| Miss 题 | 模式 | BM25 | Vector | Hybrid | 根因 |
|---|---|---|---|---|---|
| amp-001 | Hybrid 退步 | rr=0.2 | Hit@1 | Hit@2 | RRF 将 BM25 高分的错误 chunk 推到 Top-1 |
| amp-008 | 全 Miss | Miss | Miss | Miss | "认证" vs "FCC WARNING" 语义gap + 分块问题 |
| amp-013 | Hybrid 退步 | Miss | Hit@1 | Hit@2 | BM25 干扰，表格内容 SNR 关键词被 HTML 淹没 |
| amp-024 | Vector Miss | Hit@1 | Miss | Miss | "保存调音设置"语义不精确，BM25 靠"保存+Flash"词匹配反而成功 |

**失败模式归纳：**
- **Hybrid 退步**（amp-001, amp-013）：BM25 高分错误结果通过 RRF 干扰 Vector 的正确排序 → 需调 RRF k 值
- **全 Miss**（amp-008）：语义和关键词都无法匹配 → 需分块/标题优化
- **Vector 独 Miss**（amp-024）：操作步骤类问题，语义模型不理解"保存设置"的意图 → BM25 反而有优势

### 3. 按题目类别的通过率

| 类别 | 总题数 | Hybrid 通过 | 通过率 | 分析 |
|---|---|---|---|---|
| specs（规格参数） | 5 | 4 | 80% | amp-001 Hybrid 退步 |
| usage（基础使用） | 3 | 3 | 100% | 全部命中 |
| usage-complex（复杂操作） | 2 | 1 | 50% | amp-024 Miss |
| table-extraction（表格） | 3 | 2 | 67% | amp-013 Hybrid 退步 |
| multi-hop | 1 | 1 | 100% | OK |
| negation | 1 | 1 | 100% | OK |
| synonym | 1 | 1 | 100% | OK |
| reasoning | 1 | 1 | 100% | OK |
| troubleshooting | 1 | 1 | 100% | OK |
| policy/commercial | 2 | 2 | 100% | OK |
| compliance | 1 | 0 | 0% | amp-008 全 Miss |
| specs-implicit | 1 | 1 | 100% | OK |
| out-of-scope | 2 | N/A | — | 测试项 |

**薄弱环节**：compliance（0%）、usage-complex（50%）、table-extraction（67%）、specs Hybrid退步

## 改进建议（更新）

| 优先级 | 改进项 | 预期收益 | 受影响 case |
|---|---|---|---|
| P0 | RRF k 参数调优（当前默认 60） | 修复 amp-001, amp-013 Hybrid 退步 | 2 题 |
| P1 | BM25 索引前 strip_html() | 消除 HTML 噪声，表格检索提升 | amp-013 等 |
| P2 | FCC/合规段落分块优化：保留 section 标题 | amp-008 命中 | 1 题 |
| P3 | BM25 chunk 拼入 section path | BM25 整体提升 | 多题 |
| P4 | 操作步骤类内容增强（chunk 元数据加 step 标签） | amp-024 Vector 命中 | 1 题 |
