# Backend

FastAPI 服务，负责：
- LangGraph 状态机编排（规划 TODO、检索、评估、写作）
- 私有资料上传与本地检索（BM25 + ChromaDB 语义检索）
- 任务状态持久化（文件式存储）
- SSE 事件流：向前端推送节点与 tool call 状态

## 运行
1) 安装依赖：`pip install -e .`
   - 使用本地 Embedding（`EMBEDDING_PROVIDER=local`）时：`pip install -e ".[local_embedding]"`
2) 启动：`uvicorn app.main:app --reload --port 8000`

如果你需要手动激活虚拟环境：
- PowerShell：`. .\\.venv\\Scripts\\Activate.ps1`
- CMD：`.\\.venv\\Scripts\\activate.bat`

## API 速览
- `POST /api/jobs`：创建任务
- `POST /api/jobs/{job_id}/start`：启动研究（后台线程）
- `POST /api/jobs/{job_id}/uploads`：上传资料（PDF/文本/图片）
- `POST /api/jobs/{job_id}/interact`：随时提问/提要求（可新增 TODO、生成回答）
- `GET /api/jobs/{job_id}/events/stream`：SSE 事件流
- `GET /api/tools` / `POST /api/tools/reload`：MCP 工具列表与热重载

## 环境变量
复制 `../.env.example` 为 `../.env` 并按需填写：
- Web Search：`WEB_SEARCH_PROVIDER=tavily` + `TAVILY_API_KEY=...`
- LLM：`LLM_PROVIDER=openai|moonshot|deepseek` + `LLM_API_KEY/LLM_MODEL/LLM_BASE_URL`
- Embedding（RAG）：OpenAI 兼容用 `EMBEDDING_PROVIDER=openai` + `EMBEDDING_MODEL=...`；本地模型用 `EMBEDDING_PROVIDER=local` + `EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5`（可选 `EMBEDDING_DEVICE=cpu|cuda`）
- Redis 缓存（可选）：`REDIS_URL=redis://localhost:6379/0`（可选 `REDIS_PREFIX/REDIS_JOB_TTL_SECONDS`）
