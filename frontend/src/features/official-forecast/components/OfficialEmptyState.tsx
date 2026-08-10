import { SafetyCertificateOutlined } from "@ant-design/icons";
import { Tag } from "antd";

import styles from "./OfficialUi.module.css";

export default function OfficialEmptyState({
  title,
  detail,
  status,
}: {
  title: string;
  detail: string;
  status?: string;
}) {
  return (
    <section className={styles.emptyState}>
      <SafetyCertificateOutlined />
      <h2>{title}</h2>
      <p>{detail}</p>
      {status ? <Tag>STATUS: {status}</Tag> : null}
    </section>
  );
}
