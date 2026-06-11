import { Spin } from 'antd';

/** 路由懒加载 fallback（FE-7） */
export function PageLoader() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 240 }}>
      <Spin size="large" />
    </div>
  );
}
