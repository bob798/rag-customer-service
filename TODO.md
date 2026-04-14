# 项目开发 TODO

> 开发状态快照。完成项移入 CHANGELOG.md，新想法先加到「待评估」区。

---

## 当前版本状态

| 版本 | 里程碑 | 测试 | 分支 |
|------|--------|------|------|
| v0.1.0 | RAG 核心链路 | 160 passed | main |
| v0.2.0 | 完整 API 层 | 179 passed | main (PR #3 已合并) |
| v0.3.0-dev | 中文解析改造 + MinerU/PaddleOCR Parser + 回归测试 | 284 passed | main + feat/paddleocr-parser |

---

## 🔥 今晚推进（按优先级排序）

### P0：让系统能正常回答问题（0.5 天）

> E2E 评测 33% 召回率的根因不是解析质量，是阈值和 prompt 太保守

- [ ] **调 ConfidenceEvaluator 阈值**：当前 rerank_score < 0.3 就判低信心走 fallback，调低阈值或改为 multi-chunk 评估
  - 文件：`core/rag/confidence.py`
  - 参考：`docs/research/procedural-qa-in-rag.md` 断点 5
- [ ] **调 Generator prompt**：当前"只根据参考资料回答"太严，加"尽量基于资料回答，不确定时标注"
  - 文件：`prompts/generator.yaml`
- [ ] **top_k 从 5 提到 8**：流程类问题需要更多 chunk 覆盖
  - 文件：`core/rag/pipeline.py:118`
- [ ] **重跑 E2E 评测**，目标：召回率 70%+
  - 命令：`.venv/bin/python scripts/eval/eval_production_pipeline.py`

### P1：合并代码，清理分支（0.5 小时）

- [ ] 合并 `feat/paddleocr-parser` worktree 到 main（311 passed，PaddleOCRParser + .env.example + mermaid 架构图）
- [ ] 清理 worktree：`git worktree remove ../.worktrees/rag-paddleocr`
- [ ] 推送 main

### P2：Windows 跑 PaddleOCR 真实评测

- [ ] Windows 机器 clone + checkout `main`
- [ ] 运行 `scripts/eval/setup_windows.bat`
- [ ] 运行 `scripts/eval/eval_paddleocr_parsing.py`
- [ ] 拷回 `paddleocr_parsing_result.json`，对比 DefaultParser 差异

### P3：流程类 QA 的 prompt 优化（1 小时）

- [ ] Generator prompt 加"操作类问题按步骤输出"
  - 文件：`prompts/generator.yaml`，新增 `procedural` variant
- [ ] 检索结果按 `(doc_id, chunk_index)` 排序恢复原文顺序
  - 文件：`core/rag/generator.py` 的 `_build_context()`
- [ ] QueryRewriter 切换 `synonym_expansion` variant
  - 文件：`core/rag/pipeline_builder.py`

---

## 检索质量提升（研究 → 实施）

> 详细分析见 `docs/research/rag-retrieval-quality.md`

### 近期可做（低成本高收益）

- [ ] **知识库同义词增强**：FAQ 条目里写全同义词覆盖
  - 例：`Q: 音箱/音响/扬声器/喇叭 没有声音/不出声 怎么办？`
  - 预期提升：+20%+ 命中率，零计算成本

- [ ] **QueryRewriter 切换为 synonym_expansion variant**
  - 文件已就绪：`prompts/query_rewriter.yaml`
  - 修改 `pipeline_builder.py` 传入 `variant="synonym_expansion"`
  - 需要先跑 `scripts/test_synonym_retrieval.py` 验证 LLM 改写效果

- [ ] **实测 synonym_expansion 对命中率的提升**
  - 运行：`.venv/bin/python scripts/test_synonym_retrieval.py`
  - 对比：normalize vs synonym_expansion vs 无改写

### 中期（需要设计）

- [ ] **HyDE 模式实验**：LLM 生成假设答案文档再检索
  - 适合无明显同义词但概念跨度大的查询
  - 需要在 pipeline 中增加 HyDE 路径

- [ ] **RAG-Fusion**：生成多个 query 变体分别检索后 RRF 融合
  - 最高召回率提升，但 LLM 调用次数 ×N

- [ ] **领域同义词词典**：结构化维护，注入 domain_aware prompt

---

## 测试覆盖缺口（Phase 1 遗留）

> 记录于 `test-validation-plan.md`，Week 2 完成后处理

- [ ] **检索排名质量测试**：同主题歧义词（"音箱/音响"、"屋顶/吊顶/房顶"）
  - 测试框架已有，需要添加领域 FAQ 数据
  - `tests/smoke/` 新增 `test_retrieval_ranking.py`

- [ ] **Demo 场景扩展**：`scripts/demo_pipeline.py` 覆盖 medium/low confidence、ambiguous 意图
  - 当前 demo 只有 in_scope + out_of_scope 两个场景

---

## 工程债务 / 待改进

- [ ] `IntentClassifier` / `Generator` 也支持从 YAML 加载 prompt
  - `prompts/intent_classifier.yaml` 和 `prompts/generator.yaml` 已创建
  - 待修改对应组件加载逻辑（参考 `QueryRewriter` 实现）

- [ ] API 健康检查增强：`/health` 目前 `llm: "unknown"`，可加简单 ping 验证

- [ ] 文档同步：README 的接口表格补全响应体格式

---

## 文档解析改进（分阶段）

> 升级方案见 `docs/research/multimodal-document-parsing.md`

### 阶段 0：纯文本解析修复 ✅ 已完成

- [x] **修复中文分块**：`SemanticChunker` 改为字符计数 `len(text)`，默认 chunk_size=500, overlap=50
- [x] **修复中文 overlap**：`_add_overlap` 改为字符切片 `chunks[i-1][-overlap:]`
- [x] **中文句终符切分**：新增 `_split_long_paragraph()`，按 `。！？；` 切分超长段落
- [x] **Metadata 统一**：DefaultParser/FAQParser 输出统一包含 content_type/page/section
- [x] **MinerU Parser**：新建 `core/knowledge/parsers/mineru.py`，content_list 多模态分流
- [x] **回归测试**：284 用例全通过（含 68 个 PDF 解析专项测试）
- [ ] **DOCX 表格提取**：`DefaultParser._extract_docx` 补充 `table.rows` 遍历
- [ ] **FAQParser 格式扩展**：支持编号式 `1. Q: ...` 和英文 `Question:/Answer:` 格式

### 阶段 1：MinerU 部署（需 Docker，本机 torch 2.2.2 不支持）

- [ ] Docker 容器中安装 MinerU（`uv pip install "mineru[pipeline]"`）
- [ ] 验证 MinerU CLI 解析功放说明书.pdf → content_list.json
- [ ] 将真实 content_list.json 加入 tests/data/ 作为 smoke test 输入
- [ ] 表格 HTML 结构保留、图片提取、section path 端到端验证

### 阶段 2：DOCX 解析（python-docx + PaddleOCR）

> 调研记录见 `.omc/research/docx-parsing-research.md`

- [x] **DocxParser 核心**：python-docx 提取文本/表格 + PaddleOCR OCR 图片中文字
- [x] **图文位置保留**：遍历 `doc._element.body` 保持文档顺序（参考 RAGFlow）
- [x] **上下文融合**：图片/表格 chunk 包含前后文本（context_above/below, 150 字符）
- [x] **合并单元格去重**：`id(cell._tc)` 去重，避免 markdown 表格重复内容
- [x] **图片大小保护**：超过 20MP 的图片跳过 OCR，防止 OOM
- [x] **单元测试 25 个 + 真实文档冒烟测试 6 项全通过**
- [ ] **嵌套表格**：表格内嵌套的子表格当前只提取 `.text`（结构丢失）
- [ ] **VML 旧格式图片**：Word 2003 兼容模式的 `<v:imagedata>` 未处理
- [ ] **脚注/尾注**：存储在独立 OOXML part 中，当前未遍历
- [ ] **文本框**：`<w:txbxContent>` 浮动文本框内容未提取
- [ ] **图文关系标注**：识别 "如图X所示" 等引用，建立显式关联

### 阶段 3：Vision LLM 增强

- [ ] Vision LLM (claude-haiku-4-5) 描述无文字图片（成本可控）
- [ ] MinerU 内置 PaddleOCR 处理 PDF 图片文字

### 阶段 4：Contextual Retrieval

- [ ] 导入时用 LLM 给每个 chunk 加上下文前缀（Anthropic 方案，-67% 检索失败率）

## 待评估（想法池）

- [ ] 支持 PDF/DOCX 完整文档上传（当前有 DefaultParser 但未充分测试）
- [ ] 会话超时清理（长期不活跃 session 归档）
- [ ] 多租户支持（不同业务线隔离知识库）
- [ ] 管理后台 UI（当前只有 Swagger /docs）
- [ ] 流量日志 / 问题统计报表

---

## 已完成（存档）

- [x] Phase 1：RAG 全链路（IntentClassifier/QueryRewriter/HybridRetriever/BGEReranker/ConfidenceEvaluator/Generator）
- [x] Week 2：API 层（/chat SSE + 知识库管理 + 会话历史 + 配置 + 两层认证）
- [x] Prompt 可配置化：`prompts/` 目录 YAML 结构，QueryRewriter 支持多 variant
- [x] 检索质量研究基础设施：`scripts/test_synonym_retrieval.py` + `docs/research/`
