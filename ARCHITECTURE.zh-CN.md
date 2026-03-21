# Multi-Agent Research Assistant 项目与架构详解（面向理工科入门读者）

> 目标读者：具备基础编程能力（会写 Python/JS、懂一点 HTTP、用过 Git）的普通理工大学生。  
> 阅读目标：读完后你能理解这个项目“从前端点一下开始，到后端生成报告”的整条链路，知道每个模块在做什么，并能在需要时改出自己的功能。

---

## 0. 这到底是个什么项目？一句话版

这是一个“**TODO 驱动的多智能体研究助手**”：用户给一个研究问题（Query），系统会把问题拆成若干个 TODO（子任务），对每个 TODO 去检索资料、做摘要笔记，最后把所有笔记整合成一篇结构化报告，并把过程中的事件（节点开始/结束、工具调用、失败原因等）实时推送到前端页面。

它主要由两部分组成：

- **后端（backend/）**：FastAPI 提供 HTTP API；LangGraph 负责“研究流程状态机”；RAG（私有资料检索）+ Web Search（公开检索）+ MCP（可插拔工具）为流程提供“外部能力”；文件式存储保存任务状态与事件。
- **前端（frontend/）**：Vue 3 单页应用；创建任务、上传资料、启动研究；通过 SSE 订阅事件流，实时显示进度、TODO、笔记与报告。

如果你把它想象成一个“自动做作业”的流水线：

1. 你提出题目（Query）
2. 它列出小步骤（TODO 列表）
3. 每一步去查资料（Web/私有资料/MCP）
4. 写每一步的小结（Note）
5. 把所有小结整理成报告（Report）
6. 全程把“我现在做到哪了”实时通知你（SSE 事件流）

---

## 1. 关键概念与术语表（先把名词对齐）

为了让后面的架构解释更顺畅，这里先把本项目里最核心的几个概念解释清楚：

### 1.1 Job：一次完整研究任务

**Job** 可以理解为“一个研究项目实例”。你在前端输入一个问题并点击创建，就会生成一个 Job。

Job 的状态一般是：

- `created`：创建完成但没开始
- `running`：正在执行
- `succeeded`：成功完成
- `failed`：失败（通常是外部依赖出错，如 LLM/搜索服务报错）

### 1.2 Todo：子任务列表

系统会把 Query 拆成多个 **Todo**。每个 Todo 有自己的状态：

- `pending`：待执行
- `in_progress`：执行中
- `done`：已完成（通常意味着已经产出一条 Note）

### 1.3 Source：资料来源（证据）

每个 TODO 会收集一些 **Source**（来源），来源可能来自：

- Web Search：公开网页搜索（例如 Tavily / DuckDuckGo）
- Private Knowledge：你上传的私有资料（PDF/文本/图片 OCR）
- MCP Tool：企业工具/内部系统（本项目提供 demo MCP server）

Source 里不仅保存标题/URL/摘要，还会有一个 `quality_score`（0~1），用来在后续摘要时优先选取更可靠的来源。

### 1.4 Note：对某个 Todo 的研究笔记

**Note** 是对“某条 Todo”的阶段性输出，通常是 Markdown 文本，包含要点、解释、引用来源 id 列表等。

### 1.5 Report：最终报告

**Report** 是把所有 Note 进行整合后的最终长文（Markdown）。默认结构包含摘要、背景、方法/现状、关键发现、证据表、风险与局限、结论与下一步等。

### 1.6 Tool Call：工具调用（可观测性）

本项目为了让前端能实时看到“后端在做什么”，把很多动作都抽象成“工具调用事件”：

- `web.search`：公开搜索
- `kb.bm25_search`：对私有资料做 BM25 检索（本地词法检索）
- `kb.vector_search`：对私有资料做向量检索（语义检索）
- `llm.chat`：调用 LLM 生成 TODO/笔记/报告/事实核查
- `demo.sql_query`：MCP demo 工具

注意：这里的“tool”有两层含义：

1. **真实可调用工具**：例如 `web.search` 可以通过后端的 ToolRegistry 调用。
2. **仅用于记录的伪工具**：例如 `kb.bm25_search` 是内部逻辑，不一定暴露为 `/api/tools/call` 的可调用工具，但会在事件里出现，用于可观测性。

### 1.7 SSE（Server-Sent Events）：后端到前端的“单向实时推送”

SSE 是一种轻量的实时推送方式：浏览器和后端建立一个长连接，后端不断推送事件，前端实时显示进度。

你可以把 SSE 看成“后端在群里不断发消息”，前端只负责接收和展示，不需要反向推送。

---

## 2. 项目目录结构：从顶层开始认识代码

项目根目录大致是这样：

- `backend/`：后端服务（FastAPI + LangGraph）
- `frontend/`：前端应用（Vue 3 + Vite）
- `scripts/`：开发辅助脚本（Windows PowerShell）
- `assets/`：示例输入/静态资源（可选）
- `data/`：运行时数据目录（任务 JSON、上传文件、索引、ChromaDB 持久化等）
- `.env` / `.env.example`：环境变量配置
- `mcp_servers.json`：MCP server 配置（可插拔工具）

建议你先从这几份文件入手（它们几乎就是“项目说明书 + 入口”）：

- `README.md`：项目总体介绍（如果你看到乱码，说明文件编码需要你的编辑器按 UTF-8 打开）
- `backend/README.md`：后端运行方式
- `frontend/README.md`：前端运行方式
- `backend/app/main.py`：FastAPI 应用入口
- `backend/app/research/graph.py`：LangGraph 流程核心

---

## 3. 从“点按钮”到“出报告”：端到端数据流（最重要的一节）

这一节我们用“用户视角 + 系统视角”把整条链路走一遍。建议你边读边打开对应文件。

### 3.1 用户在前端做了什么？

前端的两个主要页面：

- `frontend/src/pages/NewJob.vue`：创建新 Job（输入问题和设置）
- `frontend/src/pages/JobDetail.vue`：查看 Job（TODO、笔记、报告、事件流、上传）

典型动作是：

1. 在 `NewJob` 输入研究问题，点击创建
2. 跳转到 `JobDetail`
3. 可选：上传 PDF/文本/图片，作为私有资料
4. 点击“开始研究”
5. 观察 TODO、笔记、报告逐步出现；下方 SSE 事件不断刷新

### 3.2 后端有哪些 API？

后端 API 主要在 `backend/app/api/` 下：

- `POST /api/jobs`：创建 Job
- `GET /api/jobs/{job_id}`：获取 Job 当前状态（包含 todos/notes/sources/report/events）
- `POST /api/jobs/{job_id}/start`：启动研究（后台线程执行）
- `POST /api/jobs/{job_id}/uploads`：上传并解析资料（写入私有知识库）
- `GET /api/jobs/{job_id}/events/stream`：SSE 事件流（实时推送）
- `GET /api/tools` / `POST /api/tools/reload` / `POST /api/tools/call`：工具列表、热重载、调用

### 3.3 Job 数据存在哪里？

这个项目为了简单（KISS），没有用数据库，而是用文件保存状态：

- `data/jobs/{job_id}.json`：Job 的完整状态（包含 todos/notes/sources/report/events）
- `data/uploads/{job_id}/...`：上传的原始文件
- `data/kb/{job_id}.jsonl`：BM25 的本地索引（按 chunk 逐行写入）
- `data/chroma/{job_id}/...`：ChromaDB 向量库持久化目录

文件式存储的好处是：

- 容易理解、易调试（打开 JSON 就能看任务状态）
- 无需部署数据库，适合教学/原型

缺点是：

- 并发能力一般（需要自己做好锁）
- 数据量大后管理不如数据库方便

本项目通过 `JobStore` 做了基本并发保护（同一 job_id 使用 RLock）。

### 3.4 研究流程是怎么跑的？（LangGraph 状态机）

核心流程在 `backend/app/research/graph.py`，它不是“一条直线脚本”，而是一个**状态机**（State Machine）：

```text
plan  -> next_todo -> retrieve -> synthesize -> next_todo -> ... -> report -> fact_check -> END
```

你可以把它理解为：

- `plan`：先规划 TODO 列表
- `next_todo`：挑下一条 pending TODO 标记为 in_progress
- `retrieve`：为当前 TODO 收集资料（web + private + mcp）
- `synthesize`：基于资料写一条 Note，并把该 TODO 标记 done
- 循环直到没有 pending TODO
- `report`：把所有 Note 汇总成最终报告
- `fact_check`：对报告做事实核查/引用校对（可在 settings 关闭）

这些节点之间的跳转由 LangGraph 管理，你不需要手写复杂的 while/if 嵌套。

### 3.5 为什么要做事件流？

一个典型研究任务会持续几十秒甚至更久（检索 + LLM + embedding），如果前端只靠轮询 `GET /api/jobs/{id}`，用户体验会很差，也不利于排错。

因此后端会把关键事件写入 `job.events`，并通过 SSE 推送：

- 节点开始/结束：`node_started` / `node_completed`
- TODO 状态变化：`todo_started` / `todo_completed`
- 工具调用：`tool_call_started` / `tool_call_completed` / `tool_call_failed`
- 上传解析：`upload_saved` / `upload_ingested`
- 任务开始/结束：`job_started` / `job_failed`

前端 `JobDetail.vue` 使用 `EventSource` 订阅 SSE，并在收到消息时刷新 job 状态，做到“实时进度条”的效果。

### 3.6 打开 `data/jobs` 看见“系统的大脑”（Job JSON 与事件示例）

很多同学第一次读这种系统会觉得抽象：前端点一下，后端跑半天，到底“状态”藏在哪里？  
在本项目里答案非常直观：**Job 的完整状态就落在一个 JSON 文件里**。

以 `data/jobs/{job_id}.json` 为例，你会看到它大概包含这些字段（为便于理解，这里省略了部分内容）：

```json
{
  "id": "bc_j2olROXB1JQ",
  "query": "……用户输入的问题……",
  "status": "running",
  "settings": { "max_todos": 8, "web_results_per_todo": 5, "enable_fact_check": true },
  "todos": [
    { "id": "1", "title": "……", "status": "done", "note_id": "note:1" },
    { "id": "2", "title": "……", "status": "in_progress", "note_id": null }
  ],
  "notes": [
    { "todo_id": "1", "title": "……", "content_md": "## 要点\\n...", "source_ids": ["web:1:0"] }
  ],
  "sources": [
    { "id": "web:1:0", "title": "……", "url": "https://...", "quality_score": 0.6 }
  ],
  "report": null,
  "error": null,
  "uploads": [
    { "filename": "paper.pdf", "stored_path": "…/data/uploads/…", "ingested": true }
  ],
  "events": [
    { "type": "job_started", "ts": "..." },
    { "type": "node_started", "node": "plan", "ts": "..." },
    { "type": "tool_call_started", "tool": "web.search", "args": { "query": "..." }, "ts": "..." }
  ]
}
```

读懂这份 JSON，你就能理解整个系统的“状态机”到底在干什么：

- `todos/notes/sources/report` 是“业务结果”
- `events` 是“过程日志”，能定位到具体节点/工具哪里失败了

SSE 的实现也因此非常好理解：`/events/stream` 只是把 `events` 数组按下标从 cursor 开始逐条推送给浏览器，并定期 keepalive，前端收到新事件就刷新一次 job。

---

## 4. 后端架构详解（FastAPI + LangGraph + RAG + Tools）

后端的架构核心目标很简单：**把“研究流程”当作一个可控、可观察、可扩展的工作流**。

### 4.1 FastAPI 应用入口：`backend/app/main.py`

`create_app()` 做了三件事：

1. 读取配置（`get_settings()`）
2. 配置 CORS（允许前端域名访问）
3. 挂载各个 Router（jobs/uploads/events/tools）

这意味着：你只要把后端跑起来（uvicorn），就会在 `/api/...` 得到完整接口。

### 4.2 配置系统：`backend/app/core/config.py`

这个项目用 `pydantic-settings` 从根目录 `.env` 读取环境变量。配置分为几类：

- 应用与路径：`api_prefix`、`data_dir`、`mcp_config_path`
- LLM：`LLM_PROVIDER/LLM_API_KEY/LLM_MODEL/LLM_BASE_URL`
- Embedding：`EMBEDDING_PROVIDER/EMBEDDING_MODEL/...`
- Web Search：`WEB_SEARCH_PROVIDER` 以及 Tavily 的配置

为什么要做 `resolve_llm()` / `resolve_embedding()`？

因为很多厂商都提供“OpenAI-compatible”接口，但环境变量命名不统一。这个项目通过 resolve 方法把各种配置“收敛”为统一结构：

- `provider`
- `api_key`
- `base_url`
- `model`

这样后续调用 LLM/Embedding 时，业务代码不需要关心你用的是 OpenAI、Moonshot、DeepSeek 还是别的兼容服务。

### 4.3 任务存储：`backend/app/core/storage.py`

`JobStore` 是文件式存储的封装，负责：

- `create_job()`：生成 job_id，写入初始 JSON
- `get_job()`：读取 JSON 并反序列化为 Job
- `update_job()`：读旧值，merge patch，写回 JSON
- `append_event()`：把事件 append 到 `events` 并限制最大长度（防止无限增长）

并发安全点：

- 同一个 job_id 的读写都用 `RLock` 保护，避免“读到一半写入导致 JSON 破损”。

### 4.4 研究数据模型：`backend/app/research/models.py`

后端用 Pydantic 模型定义 Job 的形状（前后端共享结构概念）：

- `JobSettings`：控制流程的开关和参数（最大 todo 数、每 todo 搜索结果数量、是否启用 fact check、是否启用 MCP 等）
- `TodoItem` / `Note` / `Source` / `UploadItem`：结构化字段
- `JobResponse`：API 返回对象（基本等于 Job）

这套模型的好处是：

- 前端 TypeScript 类型可以按这个结构写（`frontend/src/api.ts` 就是类似的结构）
- 数据落盘到 JSON 后结构清晰，易 debug

### 4.5 LangGraph 流程核心：`backend/app/research/graph.py`

#### 4.5.1 ResearchState 与 GraphContext

- `ResearchState`：状态机里的“全局状态”，包括 query、todos、sources、notes、report 等。
- `GraphContext`：不进入状态机持久化，但贯穿执行过程，用来：
  - `emit(event)`：写事件（供 SSE/调试）
  - `persist(patch)`：更新 job JSON（保存中间结果）

这个设计非常工程化：

- **状态**（state）用于计算与决策
- **副作用**（emit/persist）从状态里抽离，便于控制与替换

#### 4.5.2 每个节点做什么？

1) `plan_node`

- 输入：query + settings
- 输出：todos（优先使用 LLM 生成 JSON TODO 列表；失败则用 fallback 模板）

2) `next_todo_node`

- 在 todos 里找到第一条 `pending`，把它改成 `in_progress`，并记录当前 todo_id
- 如果找不到 pending，就返回 `current_todo_id=None`，后续会走到 `report`

3) `retrieve_node`

- 收集资料来源 sources（Web + 私有 + 可选 MCP）
- Web：调用 `web.search` 工具
- 私有：`RagSubAgent` 做 BM25 + 向量检索
- MCP：示例调用 `demo.sql_query`（可开关）

4) `synthesize_node`

- 选取本 todo 的 top sources（按 `quality_score` 排序）
- 如果 LLM 可用，调用 `llm.chat` 生成一条 Markdown note
- 如果 LLM 不可用或失败，生成占位 note（保证流程可继续）
- 写入 notes，并把 todo 标记为 `done`

5) `report_node`

- 把所有 notes 按大纲组织成报告
- 同样：LLM 成功则生成高质量报告；失败则生成占位报告（把笔记拼起来 + 列出来源）

6) `fact_check_node`

- 可选步骤（`enable_fact_check`）
- 取 top sources 做“证据列表”，让 LLM 对报告进行修订、标注来源，并输出证据表
- 如果失败或被关闭，则跳过，不影响主流程结束

#### 4.5.3 为什么要做“降级占位”？

现实中外部服务经常失败：

- 搜索 API 可能超时/限流
- LLM 可能因参数不兼容（temperature）、内容安全（content_filter）拒绝
- 本地 embedding 模型可能下载失败或机器太慢

为了不让整条任务“动不动就失败”，项目会尽量做到：

- **外部依赖失败时，流程仍能走完**（至少产出占位结果）
- **失败信息被记录到事件流**（让前端能看到工具调用失败原因，便于排障）

这也是工程上常见的“弹性设计”：核心流程要尽量可用，能力增强组件失败时要可降级。

### 4.6 LLM 客户端：`backend/app/research/llm.py`

`LlmClient.complete()` 会把 messages 转成 LangChain 的 `ChatOpenAI` 调用。

为什么要用 LangChain？

- 统一接口，支持 OpenAI-compatible 的 base_url + api_key
- 未来扩展到 tool calling 或 structured output 会更方便

本项目还做了一个现实问题的适配：**有些模型只允许 temperature=1**。因此在调用失败时会检测错误信息并自动重试（并记忆该模型后续强制 temperature=1），减少“因为小参数不兼容导致整个任务失败”的概率。

### 4.7 Web Search：`backend/app/research/web_search.py`

目前支持两种 provider：

- `duckduckgo`：本地调用 `duckduckgo-search`，无需 key（但稳定性与质量受限）
- `tavily`：需要 `TAVILY_API_KEY`，通常更稳定，支持更丰富 options
- `disabled`：完全关闭 web 搜索

它对上层暴露的是统一的 `WebResult(title, url, snippet)` 列表。

#### 4.7.1 来源质量评分：`quality_score` 怎么来的，为什么要做？

你会在 sources 里看到一个 `quality_score`（0~1），它来自 `backend/app/research/source_quality.py` 的一个非常“朴素但好用”的启发式规则：

- **高可信域名加分**：例如 `.gov`、`.edu`，或一批常见学术/机构域名（WHO、IEEE 等）
- **低可信线索减分**：例如某些博客平台域名提示
- **内容线索微调**：标题/摘要里出现 `pdf`、`peer-reviewed` 等关键词会小幅加分
- 如果完全没有信号，就给一个 baseline（默认 0.3）

它不是学术级的“可信度判别器”，但在工程上能解决一个现实问题：  
当你检索回来的来源很多时，后续写 Note/Report 不可能把所有来源都喂给 LLM，只能取 top K。  
这时 `quality_score` 就成为一个“可解释的排序依据”，让系统更倾向于引用更像论文/机构页面的来源，而不是随机网页。

### 4.8 私有知识库（RAG）：`local_knowledge.py` + `vector_knowledge.py`

上传文件后会走 `ingest_uploaded_file()`：

1. 存盘到 `data/uploads/{job_id}/...`
2. 提取文本：
   - PDF：`pypdf` 提取每页文本
   - 图片：可选 OCR（需要安装 `pillow` + `pytesseract`）
   - 文本：尝试 utf-8，失败则 latin-1
3. 写入两种索引：
   - **BM25（LocalKnowledgeBase）**：词法检索，速度快、对专有名词友好
   - **向量库（VectorKnowledgeBase + ChromaDB）**：语义检索，能匹配“同义改写”

检索时 `RagSubAgent` 会：

- 先 BM25 搜索拿到 top chunks
- 再向量搜索拿到 top chunks
- 合并成 sources，供 synthesize/fact_check 使用

你可以把它理解为：私有资料检索提供“本地证据”，让报告能引用你上传的 PDF，而不仅仅是网上搜到的网页。

### 4.9 工具系统：ToolRegistry + MCP（可插拔能力）

工具系统的目标是：让研究流程可以调用外部能力（搜索、数据库、企业系统等），并且尽量做到“插拔式”。

#### 4.9.1 ToolRegistry：内置工具注册表

`backend/app/tools/registry.py` 提供：

- 内置工具（builtin）：
  - `web.search`
  - `kb.vector_search`
- MCP 工具（mcp）：从 `mcp_servers.json` 加载

并提供 `/api/tools` 与 `/api/tools/call` 让前端/调试调用工具。

#### 4.9.2 MCP：把外部进程当成工具服务器

MCP 部分由：

- `mcp_servers.json`：配置要启动哪些 server（名称 + 命令）
- `backend/app/mcp/manager.py`：读取配置并启动子进程、管理 client
- `backend/app/mcp/client.py`：最小 JSON-RPC 客户端（stdin/stdout 通信）
- `backend/mcp_servers/demo_server.py`：示例 server（提供 echo 与 sql_query 工具）

为什么 MCP 有价值？

因为它把“工具实现”从后端主进程里拆出来：

- 你可以用任何语言写一个小进程，只要会 stdin/stdout JSON-RPC
- 后端无需改动太多，只要在配置里加一条 server
- 工具调用失败不会直接把 API 服务搞崩（最多该工具不可用）

这非常适合“企业系统集成”或“教学 demo”：你可以模拟数据库、内部搜索、文件系统等能力。

---

## 5. 前端架构详解（Vue 3 + Vite + SSE）

前端整体非常克制（KISS）：两页 + 一个 API 封装 + Markdown 渲染。

### 5.1 入口与路由

- `frontend/src/main.ts`：挂载 Vue 应用
- `frontend/src/router.ts`：两条路由：
  - `/` -> `NewJob`
  - `/jobs/:jobId` -> `JobDetail`

### 5.2 API 封装：`frontend/src/api.ts`

前端所有请求都通过 `http()` 包装：

- 成功：解析 JSON
- 失败：把 response text 抛成 Error（便于在 UI 展示）

对应后端的 job 生命周期：

- `createJob()` -> `POST /api/jobs`
- `getJob()` -> `GET /api/jobs/{id}`
- `startJob()` -> `POST /api/jobs/{id}/start`
- `uploadFile()` -> `POST /api/jobs/{id}/uploads`

### 5.3 SSE：`JobDetail.vue` 的实时刷新策略

`JobDetail.vue` 里做了两件事：

1. `EventSource("/api/jobs/{id}/events/stream")`：一旦收到 message，就触发 `refresh()`
2. 额外做了一个 `setInterval` 每 2.5s 拉一次 `getJob()`（防止 SSE 中断）

这是一种务实的策略：

- SSE 给你实时性
- 轮询给你“最终一致性”（SSE 断了也能更新）

### 5.4 前端代理与后端地址

开发环境下，Vite 会把 `/api` 代理到后端地址。

为了避免你改了后端端口后前端还固定指向 `8000`，项目支持：

- `frontend/vite.config.ts` 读取 `VITE_BACKEND_URL`，默认 `http://localhost:8000`
- `scripts/dev.ps1` 启动前端时注入该环境变量

### 5.5 Markdown 渲染与安全：为什么要 `sanitize`？

后端生成的 Note/Report 是 Markdown，前端需要把它渲染成 HTML。最直接的做法是：

1. Markdown -> HTML（比如用 `markdown-it`）
2. HTML 插入到页面（`v-html`）

但第 2 步有一个经典安全风险：**XSS**。  
如果 Markdown 里被注入了恶意的 HTML/脚本，浏览器可能会执行它。

因此本项目在 `frontend/src/lib/markdown.ts` 里做了两件事：

- 用 `markdown-it` 做渲染（方便、成熟）
- 用 `dompurify` 做清洗（把危险标签/属性移除）

对理工科同学来说，你可以记住一句话：  
**只要你要把“外部生成的内容”用 `v-html` 放进页面，就必须做 sanitize。**

---

## 6. 配置与运行：从零启动一次（不踩坑版）

### 6.1 后端启动（推荐使用 venv）

在 `backend/` 下：

1) 创建 venv（仅第一次）

```powershell
cd backend
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -e .
```

2) 启动服务

```powershell
uvicorn app.main:app --reload --port 8000
```

如果你遇到 Windows 的端口权限错误（WinError 10013），换端口即可：

```powershell
uvicorn app.main:app --reload --port 8001
```

### 6.2 前端启动

在 `frontend/` 下：

```powershell
cd frontend
npm install
npm run dev
```

浏览器打开 `http://localhost:5173`。

### 6.3 一键脚本

根目录 `scripts/dev.ps1` 支持一键启动前后端，且能传端口：

```powershell
./scripts/dev.ps1 -BackendPort 8001 -FrontendPort 5173
```

如果你要自动安装依赖：

```powershell
./scripts/dev.ps1 -Install
```

> 注意：安装依赖会下载 Python/Node 包，取决于网络环境。

### 6.4 .env 配置建议

你需要至少配置一项：

- LLM：用于生成 TODO/笔记/报告/事实核查
- Web Search：用于公开资料检索（可选）
- Embedding：用于私有资料向量检索（可选，但强烈推荐）

示例（不要把真实 key 提交到仓库）：

```ini
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=https://api.openai.com/v1

WEB_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=tvly-...

EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
EMBEDDING_DEVICE=cpu
```

### 6.5 `data/` 目录说明：如何迁移、如何“重置环境”

默认情况下，后端会把运行数据写到根目录的 `data/` 下（由 `Settings.data_dir` 控制）。  
你可以把 `data/` 理解为“运行时工作区”，里面不是源码，而是任务状态与索引：

- `data/jobs/`：每个任务一个 JSON（最重要）
- `data/uploads/`：上传的原始文件
- `data/kb/`：BM25 索引（jsonl）
- `data/chroma/`：向量库持久化目录

一些实用建议：

- 如果你要把项目拷到另一台机器继续调试，只要把 `data/` 一起拷走，历史任务也会一起带过去。
- 如果你想“从零开始”做演示/测试，清空 `data/` 就相当于清空了所有任务与上传资料（注意：这是不可恢复的操作，别在你有重要数据时这么做）。
- 更工程化的做法是：在不同实验里配置不同的 `DATA_DIR`（例如 `data-dev`、`data-demo`），互不影响。

---

## 7. 常见问题与排障（你大概率会遇到）

### 7.1 HuggingFace 警告：未认证请求

当你使用本地 embedding（例如 `BAAI/bge-small-zh-v1.5`）时，第一次会从 HF Hub 下载模型，可能看到：

- “unauthenticated requests … set HF_TOKEN …”

这不是致命错误，只是提示：

- 未登录会有更低的下载速率/更严格的限流
- 网络差时可能下载失败

解决思路：

- 配置 `HF_TOKEN`（如果你有 HF 账号）
- 或提前把模型缓存到本地（离线环境）

### 7.2 Transformers 提示：UNEXPECTED embeddings.position_ids

这类提示通常是模型权重和当前架构有一点点字段差异，但不影响推理，通常可以忽略。

### 7.3 LLM 报错：temperature only 1 is allowed

这说明你当前使用的某些模型对参数约束更严格。本项目已做自动重试与记忆（强制 temperature=1），但如果你仍遇到类似问题：

- 检查 `.env` 的 `LLM_MODEL` 与 `LLM_BASE_URL`
- 尝试换一个更兼容的模型

### 7.4 LLM 报错：content_filter / high risk

这通常是模型服务的内容安全策略触发，不一定是“你做错了”，可能是 query 或检索到的 snippet 包含敏感文本。

本项目的策略是：

- 记录 `tool_call_failed` 事件，尽量不让整个 job 直接失败
- 如果 LLM 彻底不可用，会回退到占位输出（保证你还能看到流程跑到哪）

更好的工程化做法（如果你要继续深挖）：

- 对 query/snippet 做清洗与截断
- 对敏感内容做重新表述（safety rewrite）
- 在 UI 上提示用户“当前问题触发内容安全限制”

### 7.5 Windows 端口权限错误：WinError 10013

常见原因是端口被占用或被系统保留。解决思路：

- 换端口（最快）
- 用 `netstat -ano | findstr :8000` 查占用

---

## 8. 如何扩展：把它变成“你的研究助手”

这一节给你一些清晰、低门槛的改造方向。

### 8.1 增加一个新的流程节点（LangGraph）

比如你想增加一个 `translate` 节点，把最终报告翻译成英文：

1. 在 `graph.py` 里新增 `translate_node`
2. 在 `build_graph()` 里 add_node + add_edge（例如 `fact_check -> translate -> END`）
3. 在 Job 模型里增加一个 `report_en` 字段（可选）
4. 前端展示新增字段

关键点：保持节点职责单一（SRP），输入输出都尽量结构化。

### 8.2 增加一个新的内置工具（ToolRegistry）

比如你想加一个 `web.fetch` 抓取网页正文：

1. 在 `backend/app/tools/registry.py` 的 `_builtins` 里加入新 ToolSpec
2. 实现 handler（注意超时、重试、内容长度限制）
3. 在 `retrieve_node` 或 `synthesize_node` 里调用它

### 8.3 增加一个 MCP 工具（推荐做法）

如果你要接企业数据库/内部 API，建议用 MCP：

1. 写一个独立进程（Python/Node/Go 都行）
2. 支持 `tools/list` 与 `tools/call` 两个 JSON-RPC 方法
3. 在 `mcp_servers.json` 里加一条 server 配置
4. 调用 `/api/tools/reload` 热加载

优点：不污染主服务进程，权限与依赖更可控。

### 8.4 前端增强：更像“产品”

当前前端是最小可用（MVP），你可以加：

- 进度条（根据 node/todo 状态）
- 事件过滤（只看 tool_call_failed）
- Source 详情面板（显示 snippet/质量评分原因）
- 报告导出（Markdown -> PDF）

---

## 9. 架构总结：用一句工程话收尾

这个项目的架构可以总结为：

> 用 FastAPI 提供 API，用 LangGraph 把研究流程做成可控状态机，用 ToolRegistry/MCP 把外部能力做成可插拔工具，用文件式 JobStore 让状态与事件可追踪，并用 SSE 把执行过程实时同步到前端。

如果你要把它当作课程项目/毕业设计方向，建议你重点把握三点：

1. **工作流建模**：把复杂流程拆成节点，让状态可解释、可重放
2. **检索与证据**：让报告不只是“生成”，而是“有来源支撑”
3. **可观测性**：让用户知道系统在做什么，失败时能定位问题

---

## 10. 你接下来可以怎么学（给理工科同学的路线）

如果你希望更系统地掌握这套架构，建议按顺序做这些小实验：

1. 不配 LLM，只用 fallback 跑完一次 job（理解流程骨架）
2. 配一个 LLM，让 TODO/笔记/报告真正生成（理解外部依赖）
3. 上传 PDF，观察 BM25 + 向量检索的差异（理解 RAG）
4. 写一个新的 MCP server，给 `retrieve` 加一个内部数据来源（理解可插拔工具）
5. 为事件流加一个更友好的 UI（理解可观测性与产品化）

做到第 3 步，你基本就能独立改造这个项目；做到第 5 步，你就能把它做成一个真正好用的“研究工具产品”。
