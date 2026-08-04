"use client";

import { Button, Card, DatePicker, Popover, Select, Space, Typography } from "antd";
import dayjs from "dayjs";
import type { ReactNode } from "react";

import type { TableState, WorkspacePayload } from "../../../app/shared";

const { RangePicker } = DatePicker;
const { Paragraph } = Typography;

type ForecastWorkspaceProps = {
  filters: TableState;
  filterOptions: WorkspacePayload["filterOptions"] | null;
  horizon: number;
  onApplyFilters: (updates: Partial<TableState>) => void;
  onResetFilters: () => void;
  onSyncFilters: () => void;
  onHorizonChange: (value: number) => void;
  children: ReactNode;
};

export default function ForecastWorkspace({
  filters,
  filterOptions,
  horizon,
  onApplyFilters,
  onResetFilters,
  onSyncFilters,
  onHorizonChange,
  children,
}: ForecastWorkspaceProps) {
  return (
    <div className="tab-stack">
      <Card className="content-card">
        <div className="tab-stack">
          <div className="major-tab-header">
            <div>
              <div className="eyebrow" style={{ marginBottom: 8 }}>Governed Forecast</div>
              <Paragraph className="workspace-copy" style={{ marginBottom: 0 }}>
                Forecast always resolves to PIO_Sales_Data. Brand, Model, and date filters are independent of the
                worksheet currently open in Data Workspace.
              </Paragraph>
            </div>
            <Space wrap>
              <Button onClick={onSyncFilters}>Use compatible Data Table filters</Button>
              <Popover
                title="Forecast filter and validation details"
                trigger="click"
                content={(
                  <div style={{ maxWidth: 440 }}>
                    <Paragraph>
                      Synchronization copies only official Brand (HMA/GMA/KUS), Model, and start/end dates.
                      It clears search, model year, and part filters. Forecast always uses PIO_Sales_Data plus
                      governed Wholesale history, regardless of the Data Table sheet.
                    </Paragraph>
                    <Paragraph style={{ marginBottom: 0 }}>
                      Governed validation is expanding rolling origin at H1/H2/H3. application_recent_h1 is not
                      part of the 51-fold ranking. Allocation-only diagnostics supply the held-out actual parent
                      solely to isolate share error and are not end-to-end accuracy. Reconciliation is arithmetic
                      only. Intervals use held-out residual calibration; child interval coverage remains unvalidated
                      unless independently tested.
                    </Paragraph>
                  </div>
                )}
              >
                <Button aria-label="Forecast filter and validation guide">Validation Guide</Button>
              </Popover>
              <Button onClick={onResetFilters}>Reset Forecast filters</Button>
            </Space>
          </div>
          <div className="toolbar-grid">
            <Select
              mode="multiple"
              allowClear
              maxTagCount="responsive"
              placeholder="Brand"
              optionFilterProp="label"
              popupMatchSelectWidth={false}
              value={filters.brand}
              options={[
                { label: "HMA · Hyundai Motor America", value: "HMA" },
                { label: "GMA · Genesis Motor America", value: "GMA" },
                { label: "KUS · Kia US", value: "KUS" },
              ]}
              onChange={(value) => onApplyFilters({ brand: value })}
            />
            <Select
              mode="multiple"
              allowClear
              maxTagCount="responsive"
              placeholder="Model"
              optionFilterProp="label"
              showSearch
              popupMatchSelectWidth={false}
              value={filters.model}
              options={(filterOptions?.model ?? []).map((option) => ({
                label: `${option.label} (${option.count.toLocaleString()})`,
                value: option.value,
              }))}
              onChange={(value) => onApplyFilters({ model: value })}
            />
            <RangePicker
              value={
                filters.startDate && filters.endDate
                  ? [dayjs(filters.startDate), dayjs(filters.endDate)]
                  : null
              }
              onChange={(value) =>
                onApplyFilters({
                  startDate: value?.[0]?.format("YYYY-MM-DD") ?? "",
                  endDate: value?.[1]?.format("YYYY-MM-DD") ?? "",
                })
              }
            />
            <Select
              style={{ width: 160 }}
              value={horizon}
              options={[
                { label: "1 month", value: 1 },
                { label: "3 months", value: 3 },
                { label: "6 months", value: 6 },
                { label: "12 months", value: 12 },
              ]}
              onChange={onHorizonChange}
            />
          </div>
        </div>
      </Card>
      {children}
    </div>
  );
}
