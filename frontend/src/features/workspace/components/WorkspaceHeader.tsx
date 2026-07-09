import { Select, Space, Typography } from "antd";

const { Title, Paragraph } = Typography;

interface WorkspaceHeaderProps {
  filename: string;
  headerRow: number;
  headerDepth: number;
  rowCount: number;
  sheetName: string;
  sheetNames: string[];
  onSheetChange: (value: string) => void;
}

export default function WorkspaceHeader({
  filename,
  headerRow,
  headerDepth,
  rowCount,
  sheetName,
  sheetNames,
  onSheetChange,
}: WorkspaceHeaderProps) {
  return (
    <div className="workspace-header">
      <div>
        <div className="eyebrow">Active Workspace</div>
        <Title level={2} className="workspace-title">
          {filename}
        </Title>
        <Paragraph className="workspace-copy">
          Header row {headerRow}, depth {headerDepth}, {rowCount.toLocaleString()} rows.
        </Paragraph>
      </div>
      <Space size="middle" className="workspace-controls">
        <Select
          className="sheet-select"
          value={sheetName}
          options={sheetNames.map((name) => ({ label: name, value: name }))}
          onChange={onSheetChange}
        />
      </Space>
    </div>
  );
}
