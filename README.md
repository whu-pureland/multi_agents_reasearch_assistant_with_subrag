<<<<<<< HEAD
# Multi-Agent 自动化深度研究助手

基于 TODO 驱动的多智能体研究工作流：从任务多级拆解、信息检索、私有知识对齐到结构化报告生成，通过
LangGraph 状态机编排实现端到端自动化。

## 核心工作
- TODO 驱动：规划 → 循环执行子任务 → 汇总写作的状态机工作流
- 信源质量控制：基于域名/特征的启发式评分与排序（可扩展为 LLM 评审）
- 多源检索：Web Search（DuckDuckGo）+ 私有资料检索（BM25 + ChromaDB 语义检索）
- RAG Sub-agent：私有语义检索对齐 + 报告阶段事实核查（降低幻觉，需配置 OpenAI）
- MCP 插件工具链：通过 MCP Client 动态加载外部 Skill（可热插拔接入企业数据库等）
- 监听型智能体：捕获 tool call 状态 + FastAPI SSE 推送节点化研究链路
- 可视化前端：Vue 3 + Tailwind CSS，支持实时事件流与报告预览

## 目录结构
- `backend/`: FastAPI + LangGraph 后端（任务编排、检索、报告生成）
- `frontend/`: Vue 3 + Tailwind CSS 前端（创建任务、上传资料、查看进度与报告）
- `assets/`: 示例输入与小型固定资源
- `scripts/`: 开发辅助脚本

## 快速开始
后端：
- `cd backend`
- PowerShell：`python -m venv .venv` 然后执行 `. .\\.venv\\Scripts\\Activate.ps1`
- CMD：`python -m venv .venv` 然后执行 `.\\.venv\\Scripts\\activate.bat`
- `pip install -e .`
- `uvicorn app.main:app --reload --port 8000`

前端：
- `cd frontend`
- `npm install`
- `npm run dev`

浏览器打开 `http://localhost:5173`，默认通过代理访问后端 `http://localhost:8000/api`。

可选：一键启动（Windows PowerShell）`./scripts/dev.ps1 -Install`。

## 环境变量（.env）
复制 `./.env.example` 为 `./.env`，常用配置：
- 搜索：`WEB_SEARCH_PROVIDER=tavily` + `TAVILY_API_KEY=...`（接口实现：`backend/app/research/web_search.py`）
- LLM（OpenAI 兼容）：`LLM_PROVIDER=openai|moonshot|deepseek`，并设置 `LLM_API_KEY/LLM_MODEL/LLM_BASE_URL`（或用 `MOONSHOT_API_KEY`/`DEEPSEEK_API_KEY`）
- Embedding（RAG）：OpenAI 兼容用 `EMBEDDING_PROVIDER=openai` + `EMBEDDING_MODEL=...`；本地模型用 `EMBEDDING_PROVIDER=local` + `EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5`（需要安装后端依赖：`pip install -e ".[local_embedding]"`；可选 `EMBEDDING_DEVICE=cpu|cuda`）

兼容性说明：Moonshot / DeepSeek 按 OpenAI 兼容接口接入，优先读取 `LLM_*`，同时保留 `OPENAI_*` 作为后备。
=======
# multi_agents_reasearch_assistant_with_subrag
>>>>>>> 6d1e443f449da0f897bdf0ba16c6b794b9810845
