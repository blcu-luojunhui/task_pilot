import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';

/**
 * MSW 启用策略：
 * - 通过 import.meta.env.VITE_USE_MOCKS 开关控制（默认 'true'）
 * - 一旦后端 endpoint 上线，把对应 .env 改成 false，或在 .env.local 覆盖
 * - 生产构建不引入 msw（动态 import 在 vite 下会被识别为 lazy chunk）
 */
async function bootstrap() {
  if (import.meta.env.VITE_USE_MOCKS !== 'false') {
    const { worker } = await import('./mocks/browser');
    await worker.start({
      onUnhandledRequest: 'bypass', // 没 match 的请求透传到网络（开发 proxy → Quart）
      quiet: false,
    });
  }

  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
}

void bootstrap();
