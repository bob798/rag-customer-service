# LLM 配置指南

## 一、工作原理概览

```
你的代码
  │
  ▼
LLMFactory (core/llm/factory.py)     ← 项目封装层：fallback、统一接口
  │
  ▼
LiteLLM (第三方库)                   ← 协议翻译层：统一 100+ 个 LLM 的 API 差异
  │
  ├── Anthropic API  →  Claude
  ├── OpenAI API     →  GPT-4o / GPT-4o-mini
  ├── DeepSeek API   →  deepseek-chat
  └── 通义千问 API   →  qwen-turbo / qwen-plus
```

**核心思路**：代码只写一次 `llm.complete(messages)`，LiteLLM 负责把这个调用翻译成对应提供商的 HTTP 请求格式。切换模型只需改一行配置。

---

## 二、LiteLLM 工作机制

### 模型字符串格式

LiteLLM 用 `"provider/model-name"` 格式标识模型：

```python
"anthropic/claude-3-5-sonnet-20241022"   # Anthropic
"claude-3-5-sonnet-20241022"             # Anthropic（可省略前缀）
"openai/gpt-4o"                          # OpenAI
"gpt-4o-mini"                            # OpenAI（可省略前缀）
"deepseek/deepseek-chat"                 # DeepSeek
"openai/deepseek-chat"                   # DeepSeek（通过 OpenAI 兼容接口）
"tongyi/qwen-turbo"                      # 通义千问
```

### LiteLLM 做了什么

1. **解析模型字符串** → 识别 provider
2. **从环境变量读取 API Key**（如 `ANTHROPIC_API_KEY`）
3. **将通用 messages 格式翻译** 成该 provider 的 HTTP 请求
4. **将 provider 的响应格式统一** 成 OpenAI-compatible 结构（`response.choices[0].message.content`）

对代码完全透明——`LLMFactory.complete()` 永远返回字符串，无论底层用的哪家。

---

## 三、支持的模型和配置

### 3.1 Anthropic Claude（推荐，中文效果好）

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
```

| 模型字符串 | 说明 | 速度/成本 |
|-----------|------|---------|
| `claude-sonnet-4-6` | 最新旗舰，推理强 | 慢/贵 |
| `claude-haiku-4-5-20251001` | 轻量快速 | 快/便宜 |
| `claude-3-5-sonnet-20241022` | 平衡性能 | 中等 |

### 3.2 OpenAI GPT

```bash
# .env
OPENAI_API_KEY=sk-...
```

| 模型字符串 | 说明 |
|-----------|------|
| `gpt-4o` | 旗舰，强推理 |
| `gpt-4o-mini` | 轻量，低成本 |

### 3.3 DeepSeek（国产，中文强，低成本）

```bash
# .env
DEEPSEEK_API_KEY=sk-...
```

| 模型字符串 | 说明 |
|-----------|------|
| `deepseek/deepseek-chat` | 通用对话，性价比高 |
| `deepseek/deepseek-reasoner` | 推理模型（慢）|

### 3.4 通义千问（阿里云）

```bash
# .env
DASHSCOPE_API_KEY=sk-...
```

| 模型字符串 | 说明 |
|-----------|------|
| `tongyi/qwen-turbo` | 快速廉价 |
| `tongyi/qwen-plus` | 中等 |
| `tongyi/qwen-max` | 旗舰 |

---

## 四、如何切换模型

### 方法 1：修改 .env（推荐）

```bash
# .env
DEFAULT_MODEL=claude-haiku-4-5-20251001
FALLBACK_MODEL=gpt-4o-mini
ANTHROPIC_API_KEY=sk-ant-...
```

> 注意：`.env` 中的变量名仅作应用层读取参考，需在代码中显式读取（见下方）。

### 方法 2：修改 api/main.py 中的 PipelineBuilder 调用

```python
# api/main.py（Week 2 实现时加入）
from core.rag.pipeline_builder import create_default_pipeline
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    default_model: str = "claude-haiku-4-5-20251001"
    fallback_model: str | None = None
    class Config:
        env_file = ".env"

settings = Settings()
pipeline = create_default_pipeline(
    llm_model=settings.default_model,
    llm_fallback=settings.fallback_model,
)
```

### 方法 3：直接构造（测试 / 脚本）

```python
from core.llm.factory import LLMFactory
from core.rag.pipeline_builder import create_default_pipeline

# 使用 DeepSeek 作为主模型，GPT-4o-mini 作为 fallback
pipeline = create_default_pipeline(
    llm_model="deepseek/deepseek-chat",
    llm_fallback="gpt-4o-mini",
)
```

---

## 五、每次问答 LLM 被调用几次

每个用户问题触发 **3 次 LLM 调用**：

```
用户提问
  │
  ├─ [Call 1] IntentClassifier.classify()
  │     模型：同 llm_model
  │     输入：~100 tokens（系统提示 + 问题）
  │     输出：JSON，20 tokens
  │
  ├─ [Call 2] QueryRewriter.rewrite()
  │     模型：同 llm_model
  │     输入：~80 tokens（系统提示 + 问题）
  │     输出：改写后的问题，50 tokens 以内
  │
  └─ [Call 3] LLMGenerator.generate()
        模型：同 llm_model
        输入：系统提示 + 检索到的 chunks（~800 tokens）+ 问题
        输出：回答，200~500 tokens
```

**成本优化建议**：Call 1 和 Call 2 是简单任务，可用廉价快速模型；Call 3 是主要回答，需要质量。

当前实现三次调用用同一个模型，未来可扩展为分级模型：

```python
# 未来扩展方向（当前不支持，仅示例）
intent_llm = LLMFactory(model="gpt-4o-mini")           # 便宜
rewrite_llm = LLMFactory(model="gpt-4o-mini")          # 便宜
generate_llm = LLMFactory(model="claude-sonnet-4-6")   # 质量好

pipeline = RAGPipeline(
    intent_classifier=IntentClassifier(llm=intent_llm),
    query_rewriter=QueryRewriter(llm=rewrite_llm),
    generator=LLMGenerator(llm=generate_llm),
    ...
)
```

---

## 六、Fallback 机制

`LLMFactory` 支持双模型 fallback：

```python
llm = LLMFactory(
    model="claude-sonnet-4-6",       # 主模型
    fallback="gpt-4o-mini",          # 备用（主模型报错时自动切换）
)
```

触发 fallback 的场景：
- API Key 无效或过期
- 模型服务不可用（5xx）
- 网络超时
- 达到速率限制（429）

fallback 只重试一次，不递归。如果 fallback 也失败，异常向上抛出，由组件层的 try/except 处理（如 `IntentClassifier` 会 fallback 到 `in_scope` 默认值）。

---

## 七、快速验证配置是否正确

```python
# scripts/test_llm.py（临时验证脚本）
import asyncio
from core.llm.factory import LLMFactory

async def main():
    llm = LLMFactory(model="claude-haiku-4-5-20251001")
    reply = await llm.complete([
        {"role": "user", "content": "你好，请回复：配置成功"}
    ])
    print(reply)

asyncio.run(main())
```

```bash
export ANTHROPIC_API_KEY=sk-ant-...
.venv/bin/python scripts/test_llm.py
# 输出：配置成功
```
