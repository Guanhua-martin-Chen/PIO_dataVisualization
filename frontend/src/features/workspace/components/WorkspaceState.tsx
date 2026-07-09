import { Alert, Button, Card, Spin } from "antd";

interface WorkspaceLoadingProps {
  message: string;
}

export function WorkspaceLoading({ message }: WorkspaceLoadingProps) {
  return (
    <div className="loading-shell" style={{ minHeight: "60vh" }}>
      <div className="loading-card">
        <Spin size="large" />
        <p className="loading-msg">{message}</p>
      </div>
    </div>
  );
}

interface WorkspaceErrorProps {
  error: string;
  onGoHome: () => void;
}

export function WorkspaceError({ error, onGoHome }: WorkspaceErrorProps) {
  return (
    <Card className="content-card" style={{ maxWidth: 600, margin: "40px auto", textAlign: "center" }}>
      <Alert type="error" showIcon message="Failed to load Workspace" description={error} />
      <Button type="primary" onClick={onGoHome} style={{ marginTop: 24 }}>
        Go Back Home
      </Button>
    </Card>
  );
}
