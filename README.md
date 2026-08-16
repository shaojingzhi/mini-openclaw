# Mini-OpenClaw

中文 | [English](#english)

Mini-OpenClaw 是一个面向 Agent 场景的轻量级本地工作台：后端用 FastAPI 提供聊天、文件、会话与 trace 接口，前端用 Next.js 提供类似控制台的可视化界面，方便你在本地观察、调试和演示一个“可编辑记忆 + 技能 + 工作区 + 会话”的最小可用 Agent 系统。

## 功能概览

- 对话流式输出：前端通过 SSE/流式 `fetch` 消费 `/api/chat`
- 三 Agent 社区：灯塔默认接待，支持 `@火花`、`@砥石`确定性路由和一次显式 handoff
- 可编辑工作区：直接在前端查看和编辑 memory、skills、workspace 文档
- 会话管理：查看 session 列表、切换历史会话、读取消息状态
- Trace 可视化：查看运行痕迹与错误信息，便于排查问题
- 本地优先：默认运行在本机 `127.0.0.1`，方便调试和演示

## 项目结构

```text
mini-openclaw/
├── backend/          # FastAPI 后端、会话/trace/文件接口、测试
├── frontend/         # Next.js 前端控制台
├── docs/             # 补充说明与演示文档
├── scripts/          # 开发/启动脚本
└── README.md
```

## 运行环境

- Python 3.10+
- Node.js 18+
- npm 9+

## 快速开始

### 1. 安装后端依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 2. 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

### 3. 启动前后端

推荐直接使用仓库自带脚本：

```bash
./scripts/dev.sh start
```

查看状态：

```bash
./scripts/dev.sh status
```

查看日志：

```bash
./scripts/dev.sh logs
```

停止服务：

```bash
./scripts/dev.sh stop
```

## 默认地址

- 前端：`http://127.0.0.1:3004`
- 后端：`http://127.0.0.1:8002`
- 健康检查：`http://127.0.0.1:8002/health`

## 手动启动

如果你不想使用脚本，也可以手动启动：

### 启动后端

```bash
source .venv/bin/activate
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8002
```

### 启动前端

```bash
cd frontend
NEXT_PUBLIC_API_URL=http://127.0.0.1:8002 npm run dev -- --hostname 127.0.0.1 --port 3004
```

前端端口或后端端口不是默认值时，两侧必须对应：`NEXT_PUBLIC_API_URL` 指向后端地址，`MINI_OPENCLAW_CORS_ORIGINS` 包含浏览器实际打开的前端 origin。例如前端 `3000`、后端 `8103`：

```bash
MINI_OPENCLAW_CORS_ORIGINS=http://127.0.0.1:3000 \
  python -m uvicorn backend.app:app --host 127.0.0.1 --port 8103

cd frontend
NEXT_PUBLIC_API_URL=http://127.0.0.1:8103 npm run dev -- --hostname 127.0.0.1 --port 3000
```

`./scripts/dev.sh start` 会把默认或自定义前端端口同步到后端 CORS 配置，并把对应后端 URL 注入前端。

## 主要接口

- `GET /health`：健康检查
- `GET /api/agents`：列出 Agent 人格、别名与社区职责
- `POST /api/chat`：流式聊天
- `GET /api/files`：读取前端 Inspector 中文件
- `POST /api/files`：保存文件修改
- `GET /api/sessions`：列出会话
- `GET /api/sessions/{session_id}`：获取单个会话详情
- `GET /api/traces`：列出 traces
- `GET /api/traces/{trace_id}`：获取 trace 详情
- `GET /api/memory/proposals`：列出当前用户的长期记忆提案
- `POST /api/memory/projections/rebuild`：从 JSONL source of truth 原子重建记忆 projection
- `POST /api/memory/proposals/{proposal_id}/approve`：批准提案，使其在下一次聊天启动时加载
- `POST /api/memory/proposals/{proposal_id}/reject`：拒绝提案

## 三 Agent 使用方式

- 不写 mention 时由灯塔回答，负责上下文连续性和默认接待。
- 输入 `@火花` 定向获得证据检索、替代方案和机会视角。
- 输入 `@砥石` 定向获得假设、风险、矛盾和缺失验证检查。
- 灯塔可通过受控 tool 显式转交一次；目标 Agent 不能继续递归转交。聊天气泡和 trace 都会显示路由与 handoff 来源。

## 长期记忆审批

Agent 只能通过 `propose_memory_update` 创建 pending 候选，不能直接写入活跃记忆。聊天首页会弹出 review card 供用户 approve/reject；用户批准后，共享的 USER/PROJECT 层投影到 `approved_memory/`，私有的 AGENT/RELATIONSHIP 层投影到 `approved_memory/agents/{agent_id}/`。下一次聊天只注入共享记忆和当前 Agent 的私有记忆；trace 会记录 `memory_loaded`、`memory_proposal_created`、层级数量与裁剪数量，方便演示与审计。

运行时边界：`fetch_url` 只允许访问解析到公网的 HTTP(S) 地址，并会校验重定向目标；服务启动时会以 JSONL 审计记录为事实源清理遗留 transaction 文件并重建 memory projection。handoff 只会传递标为 shared 的网页或知识库证据。

`propose_memory_update` 需要模型供应商或网关支持标准 OpenAI-compatible function/tool calling。当 provider 返回缺失 `tool_call_id`、空 arguments 或非标准响应时，系统会记录 `provider_tool_call_invalid`，明确提示不能生成记忆提议，并且不会写入 proposal。

## 验证命令

后端测试：

```bash
source .venv/bin/activate
python -m unittest discover -s backend/tests -v
```

前端类型检查：

```bash
npm run typecheck --prefix frontend
```

前端构建：

```bash
npm run build --prefix frontend
```

## 适用场景

- 本地 Agent 原型开发
- Prompt / Memory / Skills 调试
- 演示一个最小可运行的 Agent UI
- 面试或作品集展示

## 说明

- 运行时生成的 session、storage、日志等内容默认不纳入版本控制
- `references/`、PDF、PRD 草稿等辅助材料也建议保留在本地，不直接进仓

---

## English

Mini-OpenClaw is a lightweight local workbench for agent-style applications. It combines a FastAPI backend with a Next.js frontend so you can inspect, edit, and demo a minimal agent system with editable memory, skills, workspace files, sessions, and traces.

## Highlights

- Streaming chat output via `/api/chat`
- Three-agent community with Lighthouse as host, deterministic mentions, and one bounded handoff
- Editable workspace files from the frontend inspector
- Session browsing and conversation state inspection
- Trace views for debugging runtime behavior and failures
- Local-first setup with sensible localhost defaults

## Repository Layout

```text
mini-openclaw/
├── backend/          # FastAPI backend, APIs, tests
├── frontend/         # Next.js frontend console
├── docs/             # Supporting docs and demo notes
├── scripts/          # Dev/startup helpers
└── README.md
```

## Requirements

- Python 3.10+
- Node.js 18+
- npm 9+

## Quick Start

### 1. Install backend dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 2. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 3. Start both services

Use the bundled helper script:

```bash
./scripts/dev.sh start
```

Check status:

```bash
./scripts/dev.sh status
```

Tail logs:

```bash
./scripts/dev.sh logs
```

Stop services:

```bash
./scripts/dev.sh stop
```

## Default URLs

- Frontend: `http://127.0.0.1:3004`
- Backend: `http://127.0.0.1:8002`
- Health check: `http://127.0.0.1:8002/health`

## Manual Startup

### Backend

```bash
source .venv/bin/activate
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8002
```

### Frontend

```bash
cd frontend
NEXT_PUBLIC_API_URL=http://127.0.0.1:8002 npm run dev -- --hostname 127.0.0.1 --port 3004
```

When either port differs from the default, keep both sides aligned: `NEXT_PUBLIC_API_URL` must point to the backend, and `MINI_OPENCLAW_CORS_ORIGINS` must include the actual frontend origin. For frontend `3000` and backend `8103`:

```bash
MINI_OPENCLAW_CORS_ORIGINS=http://127.0.0.1:3000 \
  python -m uvicorn backend.app:app --host 127.0.0.1 --port 8103

cd frontend
NEXT_PUBLIC_API_URL=http://127.0.0.1:8103 npm run dev -- --hostname 127.0.0.1 --port 3000
```

`./scripts/dev.sh start` synchronizes the default or custom frontend port with the backend CORS configuration and injects the matching backend URL into the frontend.

## Main API Endpoints

- `GET /health`
- `GET /api/agents`
- `POST /api/chat`
- `GET /api/files`
- `POST /api/files`
- `GET /api/sessions`
- `GET /api/sessions/{session_id}`
- `GET /api/traces`
- `GET /api/traces/{trace_id}`
- `GET /api/memory/proposals`
- `POST /api/memory/projections/rebuild`
- `POST /api/memory/proposals/{proposal_id}/approve`
- `POST /api/memory/proposals/{proposal_id}/reject`

## Three-Agent Usage

- Use chat normally for Lighthouse, the default continuity-focused host.
- Prefix a request with `@Spark` or `@火花` for evidence and alternatives.
- Prefix a request with `@Whetstone` or `@砥石` for assumption and risk checks.
- Lighthouse may request one explicit handoff. The target cannot delegate recursively, and both chat messages and traces retain provenance.

## Long-Term Memory Review

The agent can only create a pending candidate through `propose_memory_update`; it cannot directly write active memory. Shared USER/PROJECT layers are projected under `approved_memory/`, while private AGENT/RELATIONSHIP layers are projected under `approved_memory/agents/{agent_id}/`. The next bootstrap injects shared memory plus only the active agent's private memory, while traces retain loading and proposal provenance.

Runtime boundaries: `fetch_url` only reaches HTTP(S) addresses that resolve publicly and validates every redirect target. On startup, JSONL remains the source of truth: stale transaction artifacts are removed and memory projections are rebuilt. Handoffs forward only shared web or knowledge-base evidence.

## Verification

Backend tests:

```bash
source .venv/bin/activate
python -m unittest discover -s backend/tests -v
```

Frontend typecheck:

```bash
npm run typecheck --prefix frontend
```

Frontend build:

```bash
npm run build --prefix frontend
```

## Good Fit For

- Local agent prototyping
- Prompt / memory / skills debugging
- Demoing a minimal agent UI
- Interview or portfolio walkthroughs

## Notes

- Runtime-generated sessions, storage, and logs are intentionally not tracked
- Local reference files, PDFs, and draft PRDs are better kept out of git by default
