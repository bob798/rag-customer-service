# 中文文档解析工具选型

> 调研日期：2026-04-08 | 定位：通用技术选型参考
> 信息来源：OmniDocBench CVPR 2025、PDF Parsing Comparative Study (arxiv 2410.09871)、各工具官方文档

---

## 一、中文文档解析的核心挑战

| 挑战 | 说明 | 英文场景是否存在 |
|------|------|----------------|
| **表格结构丢失** | PDF 表格提取后行列关系被拉平为纯文本 | 同样存在 |
| **图片内容丢失** | 嵌入图片中的文字、图表含义完全被忽略 | 同样存在 |
| **多栏布局错乱** | 双栏/三栏 PDF 文字提取后左右交叉，阅读顺序混乱 | 同样存在 |
| **扫描件 OCR 质量** | 中文字形复杂、竖排/双栏/印章干扰，识别错误率高 | 中文更严重 |
| **中文分词缺失** | 无空格天然分隔，影响后续 token 计数和分块 | 中文特有 |
| **公式/特殊符号** | 数学公式、化学式提取为乱码或丢失 | 同样存在 |
| **混合语言** | 中英混排文档（技术手册常见），编码和排版规则不统一 | 中文特有 |

**核心认知**：中文文档解析的难度 > 英文。OmniDocBench 评测显示，几乎所有解析工具的中文识别精度均低于英文。

---

## 二、主流开源工具对比

### 2.1 OmniDocBench CVPR 2025 排行榜（复合得分）

| 排名 | 工具 | 复合得分 | 表格 TEDS | 布局 mAP | 开源 |
|------|------|---------|-----------|---------|------|
| 1 | **PaddleOCR PP-StructureV3** | **92.86** | **93.52** | — | ✅ |
| 2 | Mathpix | ~91 | — | — | ❌ 商业 |
| 3 | **MinerU 2.5** | **90.67** | — | **97.5** | ✅ |
| — | Marker 1.8.2 | 中等 | 有差距 | — | ✅ |
| — | Docling 2.14 | 中等 | 中等 | — | ✅ |
| — | PyMuPDF (get_text) | 低 | 极差 | — | ✅ |

### 2.2 综合能力对比

| 工具 | 中文文本 | 表格提取 | 扫描件/OCR | 布局理解 | 输出格式 | 速度 | 部署复杂度 |
|------|---------|---------|-----------|---------|---------|------|-----------|
| **PyMuPDF** | 良好 | ❌ 拉平 | ❌ | 无 | 纯文本 | 极快 | 极低（pip） |
| **pdfplumber** | 良好 | ✅ 坐标精确 | ❌ | 无 | 纯文本/表格 | 快 | 极低（pip） |
| **MinerU** | **优秀** | ✅ HTML | ✅ PaddleOCR | ✅ 优秀 | **Markdown/JSON** | 中等 | 中（需模型） |
| **PaddleOCR PP-StructureV3** | **优秀** | **优秀** | **优秀** | ✅ | 结构化 | 中等 | 中（需 PaddlePaddle） |
| **Docling** (IBM) | 良好 | ✅ TableFormer | ✅ | ✅ | **DoclingDocument** | 慢 | 中 |
| **Unstructured** | 良好 | ✅ | 有限 | ✅ | **Elements** | 慢 | 高（hi_res 需模型） |
| **Marker** | 良好 | 中等 | ✅ | ✅ | Markdown | 中等 | 中 |

### 2.3 各工具核心特点

**MinerU** (opendatalab/MinerU)
- 中文场景最推荐的开源端到端方案
- 内置 PaddleOCR，引入即获得最佳中文 OCR
- 输出结构化 Markdown：标题层级、表格 HTML、图片描述、公式 LaTeX
- v3.0：滑动窗口降低长文档内存峰值，支持多 GPU 部署
- 布局检测 mAP 97.5，业界最高

**PaddleOCR PP-StructureV3** (PaddlePaddle/PaddleOCR)
- OmniDocBench 综合第一，中文 OCR 最强
- 模块化：检测 + 识别 + 版面分析 + 表格识别，可单独使用
- 支持 109 种语言，竖排/双栏/印章均可处理
- 2025 年 5 月发布 PP-OCRv5，持续迭代

**Docling** (IBM)
- TableFormer 表格识别精度高，学术/科学文档强
- 输出 DoclingDocument 对象，结构化程度最高
- 与 LlamaIndex/LangChain 有原生集成
- 速度偏慢

**Unstructured**
- 最通用的文档解析框架，自动识别块类型（Title/NarrativeText/Table/Image）
- hi_res 策略需要额外模型，fast 策略质量一般
- 商业版（Unstructured API）质量更好
- 适合需要统一处理多种格式的场景

**Marker**
- PDF → Markdown 转换，保留结构
- 书籍/学术 PDF 效果好
- 表格识别能力中等

**PyMuPDF / pdfplumber**
- 轻量级，纯 Python，无模型依赖
- PyMuPDF 极快但只提取可复制文字
- pdfplumber 表格提取精确（基于坐标），但仅限数字原生 PDF
- 适合简单文档或作为 pipeline 的基础层

---

## 三、中文 OCR 方案对比

当文档包含扫描件或图片时，OCR 是必经环节：

| 工具 | 中文准确率 | 复杂排版 | 竖排/双栏 | 安装复杂度 | 推荐度 |
|------|-----------|---------|----------|-----------|--------|
| **PaddleOCR v3** | 极高 | 优秀 | ✅ | 中（pip） | ⭐⭐⭐⭐⭐ |
| EasyOCR | 良好 | 中等 | 有限 | 低 | ⭐⭐⭐ |
| Tesseract | 中等 | 差 | 差 | 低 | ⭐⭐ |
| Mathpix | 极高（公式强） | 优秀 | ✅ | API 调用 | ⭐⭐⭐⭐（商业） |
| surya | 良好 | 良好 | ✅ | 中 | ⭐⭐⭐⭐ |

**结论**：中文 OCR 首选 PaddleOCR，MinerU 内置了它。

---

## 四、选型决策树

```
你的文档是什么类型？
│
├── 纯文字（TXT/简单 PDF）
│   └── PyMuPDF / pdfplumber → 够用
│
├── 数字原生 PDF，含表格
│   ├── 只需要表格 → pdfplumber（坐标精确）
│   └── 需要完整结构 → MinerU 或 Docling
│
├── 扫描件 / 图片
│   ├── 中文为主 → MinerU（内置 PaddleOCR）或直接 PaddleOCR
│   └── 英文为主 → Marker / Docling / surya
│
├── 图文混排 / 复杂排版
│   ├── 批量处理 → MinerU（结构化输出 + OCR）
│   └── 少量高质量 → Vision LLM 整页理解（成本高）
│
└── 多格式混合（PDF + DOCX + HTML + ...）
    └── Unstructured（统一抽象层）或 MinerU（原生多格式）
```

---

## 五、业界生产实践模式

阿里/腾讯/字节等大厂的公开实践呈现共同模式：

1. **文档 → Markdown**：用中文优化解析器（MinerU 或自研）统一转为 Markdown，保留标题层级、表格 HTML
2. **元数据富化**：分块时注入 source_title、章节路径、页码，用于检索过滤和溯源
3. **表格单独处理**：转 HTML 后连同上下文描述一起存储为独立 chunk
4. **图片 VLM 描述**：用 Vision LLM 生成描述文本后拼接至相关段落
5. **混合检索**：BM25（关键词）+ Dense Retrieval（语义）
6. **二阶段 Reranker**：cross-encoder 精排，显著提升 top-k 精度

---

## 六、关键参考资料

| 资料 | 价值 |
|------|------|
| [OmniDocBench CVPR 2025](https://arxiv.org/abs/2412.07626) | 文档解析质量权威评测 |
| [PDF Parsing Comparative Study](https://arxiv.org/abs/2410.09871) | 多工具横向对比 |
| [MinerU GitHub](https://github.com/opendatalab/MinerU) | 中文最佳开源解析器 |
| [PaddleOCR GitHub](https://github.com/PaddlePaddle/PaddleOCR) | 中文最佳 OCR |
| [Docling GitHub](https://github.com/DS4SD/docling) | IBM 结构化解析 |
| [Unstructured GitHub](https://github.com/Unstructured-IO/unstructured) | 通用解析框架 |
| [CJK text in AI pipelines (Microsoft)](https://tonybaloney.github.io/posts/cjk-chinese-japanese-korean-llm-ai-best-practices.html) | 中文处理通用指南 |
