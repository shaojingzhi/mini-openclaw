# Mini-OpenClaw

中文 | [English](#english)

Mini-OpenClaw 是一个面向 Agent 场景的轻量级本地工作台：后端用 FastAPI 提供聊天、文件、会话与 trace 接口，前端用 Next.js 提供类似控制台的可视化界面，方便你在本地观察、调试和演示一个“可编辑记忆 + 技能 + 工作区 + 会话”的最小可用 Agent 系统。

## 功能概览

- 对话流式输出：前端通过 SSE/流式 `fetch` 消费 `/api/chat`
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
npm run dev -- --hostname 127.0.0.1 --port 3004
```

## 主要接口

- `GET /health`：健康检查
- `POST /api/chat`：流式聊天
- `GET /api/files`：读取前端 Inspector 中文件
- `POST /api/files`：保存文件修改
- `GET /api/sessions`：列出会话
- `GET /api/sessions/{session_id}`：获取单个会话详情
- `GET /api/traces`：列出 traces
- `GET /api/traces/{trace_id}`：获取 trace 详情

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
npm run dev -- --hostname 127.0.0.1 --port 3004
```

## Main API Endpoints

- `GET /health`
- `POST /api/chat`
- `GET /api/files`
- `POST /api/files`
- `GET /api/sessions`
- `GET /api/sessions/{session_id}`
- `GET /api/traces`
- `GET /api/traces/{trace_id}`

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
