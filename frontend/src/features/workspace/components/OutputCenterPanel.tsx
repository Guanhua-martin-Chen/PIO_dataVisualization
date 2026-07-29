"use client";

import { Button, Card, Space, Typography } from "antd";
import { DownloadOutlined } from "@ant-design/icons";

const { Paragraph } = Typography;

type OutputCenterPanelProps = {
  onExportCsv: () => void;
  onExportXlsx: () => void;
};

export default function OutputCenterPanel({ onExportCsv, onExportXlsx }: OutputCenterPanelProps) {
  return (
    <div className="tab-stack">
      <Card className="content-card">
        <div className="major-tab-header">
          <div>
            <div className="eyebrow" style={{ marginBottom: 8 }}>Output Center</div>
            <Paragraph className="workspace-copy" style={{ marginBottom: 0 }}>
              Governed forecast downloads are centralized here. Opening Output Center reuses the current controls and
              does not run a forecast.
            </Paragraph>
          </div>
        </div>
      </Card>
      <Card className="content-card" title="Available exports">
        <Space wrap size={12}>
          <Button icon={<DownloadOutlined />} onClick={onExportCsv}>
            Current-view Forecast Center CSV
          </Button>
          <Button type="primary" icon={<DownloadOutlined />} onClick={onExportXlsx}>
            SOP Excel
          </Button>
        </Space>
        <div className="health-grid output-center-grid" style={{ marginTop: 18 }}>
          <div><span className="health-label">Current-view CSV</span><strong>Selected metric, level, filters, and point forecast months</strong></div>
          <div><span className="health-label">SOP Excel</span><strong>Executive Summary and detailed Revenue / Quantity forecast workbook</strong></div>
        </div>
      </Card>
    </div>
  );
}
