import { Tag } from "antd";

export default function PeriodBadge({ value }: { value: string }) {
  const color = value === "actual" ? "green" : value === "nowcast" ? "gold" : "blue";
  return <Tag color={color}>{value.toUpperCase()}</Tag>;
}
