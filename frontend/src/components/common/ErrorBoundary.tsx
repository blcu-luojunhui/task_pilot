import { Component, ReactNode } from 'react';
import { Result, Button } from 'antd';
import { useTranslation } from 'react-i18next';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

class ErrorBoundaryInner extends Component<Props & { t: ReturnType<typeof useTranslation>['t'] }, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: { componentStack?: string | null }): void {
    console.error('[ErrorBoundary]', error, info);
  }

  override render() {
    if (this.state.error) {
      return (
        <Result
          status="error"
          title={this.props.t('error.crashTitle')}
          subTitle={this.state.error.message}
          extra={
            <Button type="primary" onClick={() => this.setState({ error: null })}>
              {this.props.t('error.retry')}
            </Button>
          }
        />
      );
    }
    return this.props.children;
  }
}

export function ErrorBoundary({ children }: Props) {
  const { t } = useTranslation('common');
  return <ErrorBoundaryInner t={t}>{children}</ErrorBoundaryInner>;
}
