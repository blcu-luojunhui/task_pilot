# TaskPilot Web Console

> Vite + React 18 + TypeScript + Ant Design 5 + MSW
>
> 项目总览见 [README](../README.md)，接口说明见 [API Guide](../docs/api.md)

## 跑起来

```bash
# 1) 安装依赖
cd frontend
npm install

# 2) 初始化 MSW Service Worker（首次运行必须，写一个 public/mockServiceWorker.js）
npm run mock:init

# 3) 启动开发服务器（默认 http://localhost:5173）
npm run dev
```

启动后浏览器自动打开。MSW 默认开启，所有 `/api/*` 请求会被拦截并返回 mock 数据，无需后端。

## 切到真实后端

启动 Quart 后端（默认 `http://127.0.0.1:6060`），然后：

```bash
# 复制 .env.example 到 .env.local，把 VITE_USE_MOCKS 改成 false
cp .env.example .env.local
echo 'VITE_USE_MOCKS=false' >> .env.local
npm run dev
```

Vite dev server 通过 `vite.config.ts` 的 `proxy` 把 `/api` 透传到 6060。

后端已实现前端依赖的主要接口（task / agent / chat / skills / auth / runs / replay / system），完整列表见 [API Guide](../docs/api.md)。MSW 仍保留为离线开发模式：不起后端也能开发 UI。

## 构建生产产物

```bash
npm run build
```

产物落在 `frontend/dist/`，可由 Quart 同进程 static 托管：

```bash
FRONTEND_DIST=frontend/dist hypercorn app:app -c app_config.toml
```

## 目录速览

```
src/
├── api/             # API client + 类型 + 每个域的封装
├── components/      # 组件（按域分子目录）
│   ├── common/      #   通用：Layout / ErrorBoundary / EmptyState
│   └── task/        #   任务相关：状态 Tag / 列表 / 提交表单
├── hooks/           # 自定义 hook（SSE 订阅等后续加）
├── mocks/           # MSW handlers + fixtures
├── pages/           # 路由对应的页面
├── stores/          # Zustand
├── utils/           # 格式化 / 颜色 / 事件分类
├── App.tsx          # ConfigProvider + Router
└── main.tsx         # 入口（含 MSW 启动）
```

## 状态机视觉约定

| 状态 (TaskStatus) | 值 | Tag color |
|---|---:|---|
| INIT | 0 | blue |
| PROCESSING | 1 | processing (带 spinning 边) |
| SUCCESS | 2 | success (绿) |
| CANCELLED | 3 | default (灰) |
| CANCEL_REQUESTED | 4 | orange |
| FAILED | 99 | error (红) |

事件源（`source` 字段）配色：

- `task_scheduler` → 蓝
- `harness` → 紫

## 当前进度

- [x] **Phase 1 MVP 骨架** — TasksPage 列表 / 筛选 / 提交 / 取消，TaskDetail 简版 timeline
- [ ] **Phase 2** — TraceView 完整版（Timeline + Step Tree + Transcript + Stats）、Skills 调用历史抽屉、Dashboard 趋势图
- [ ] **Phase 3** — Prompt Inspector、failed tool call 重放、暗色模式
- [ ] **Phase 4** — Multi-Agent DAG（React Flow）、Runs 页

## 主要决策

- **MSW 不是测试工具** — 它是前后端并行开发的契约：前端按 mock schema 写代码，后端按同一份 schema 实现 endpoint，切换只需改一个环境变量
- **AntD 而不是 shadcn** — 表格 / 表单 / 时间线 / 抽屉全是现成的，AntD 给我们省了 70% UI 工作
- **Zustand 而不是 Redux** — Agent 事件流是高频局部更新，Zustand 的 selector 订阅性能足够，无需 RTK 的样板
- **SSE 不上 WebSocket** — 后端已实现，且只是单向流，原生 EventSource 够用
