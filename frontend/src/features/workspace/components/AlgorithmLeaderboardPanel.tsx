"use client";

import { Alert, Card, Empty, Spin, Table, Tag, Typography } from "antd";

import type { ForecastCenterPayload } from "../../../app/shared";

const { Paragraph } = Typography;

type AlgorithmLeaderboardPanelProps = {
  data: ForecastCenterPayload | null;
  loading: boolean;
};

function percent(value: number) {
  return `${(value * 100).toFixed(2)}%`;
}
export default function AlgorithmLeaderboardPanel({ data, loading }: AlgorithmLeaderboardPanelProps) {  const leaderboard = data?.summary.algorithmLeaderboard;
  const foldCounts = leaderboard?.expectedFoldCounts;
  const scope = leaderboard
    ? [
        leaderboard.target,
        leaderboard.grain,
        leaderboard.horizons?.map((value) => `H${value}`).join("/"),
        leaderboard.minimumTrainingMonths ? `${leaderboard.minimumTrainingMonths}-month minimum training` : null,
        foldCounts ? `${foldCounts["1"]}/${foldCounts["2"]}/${foldCounts["3"]} = ${foldCounts.combined} common folds` : null,
        leaderboard.coverage === undefined ? null : `${(leaderboard.coverage * 100).toFixed(0)}% coverage`,
      ].filter(Boolean).join(" · ")
    : "";

  return (
    <Spin spinning={loading} tip="Loading Brand-level evidence">
      <div className="tab-stack">
      {!leaderboard ? <Empty description="Open this tab to load Brand-level algorithm evidence." /> : <>
      <Alert
        type={leaderboard.rows.length ? "success" : "warning"}
        showIcon
        message={leaderboard.validationStatus}
        description={leaderboard.disclosure}
      />
      <Card className="content-card" title="PIO Revenue algorithm leaderboard">
        <Paragraph className="workspace-copy">
          Scope: {scope}. Source hash: {leaderboard.sourceHash}; cutoff: {leaderboard.cutoff}.
          {leaderboard.aggregation ? ` ${leaderboard.aggregation}.` : ""}
        </Paragraph>
        <Table
          size="small"
          pagination={false}
          rowKey="modelId"
          dataSource={leaderboard.rows}
          locale={{ emptyText: "Registered metrics are withheld because this request is not the exact governed scope." }}
          columns={[
            { title: "Rank", dataIndex: "rank", key: "rank", width: 70 },
            { title: "Algorithm", dataIndex: "label", key: "label", width: 240 },
            { title: "HMA WAPE", dataIndex: "hmaWape", key: "hmaWape", render: percent },
            { title: "GMA WAPE", dataIndex: "gmaWape", key: "gmaWape", render: percent },
            { title: "KUS WAPE", dataIndex: "kusWape", key: "kusWape", render: percent },
            { title: "Official Total WAPE", dataIndex: "officialTotalWape", key: "officialTotalWape", render: percent },
            { title: "Accuracy proxy", dataIndex: "accuracy", key: "accuracy", render: percent },
            { title: "Folds", dataIndex: "foldCount", key: "foldCount" },
            { title: "Coverage", dataIndex: "coverage", key: "coverage", render: percent },
            { title: "Status", dataIndex: "status", key: "status", render: (value: string) => <Tag color={value === "validated_champion" ? "green" : "blue"}>{value}</Tag> },
          ]}
          scroll={{ x: 1300 }}
        />
      </Card>
      </>}
      </div>
    </Spin>
  );
}
