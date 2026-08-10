import { Select } from "antd";

import { monthLabel } from "../formatters";

export function MonthControl({ months, value, onChange }: { months: string[]; value: string; onChange: (value: string) => void }) {
  return <Select aria-label="Forecast month" value={value} onChange={onChange} options={months.map((month) => ({ value: month, label: monthLabel(month) }))} style={{ minWidth: 190 }} />;
}

export function BrandControl({ brands, value, onChange }: { brands: string[]; value: string; onChange: (value: string) => void }) {
  return <Select aria-label="Brand" value={value} onChange={onChange} options={brands.map((brand) => ({ value: brand, label: brand }))} style={{ minWidth: 130 }} />;
}

export function LevelControl({ value, onChange }: { value: "brand-plc" | "model-plc"; onChange: (value: "brand-plc" | "model-plc") => void }) {
  return <Select aria-label="Planning level" value={value} onChange={onChange} options={[
    { value: "brand-plc", label: "Brand + PLC" },
    { value: "model-plc", label: "Brand + Model + PLC" },
  ]} style={{ minWidth: 210 }} />;
}
