"use client";

import { CloudUploadOutlined, DatabaseOutlined } from "@ant-design/icons";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { officialHref, type OfficialQuery } from "./officialQuery";
import styles from "./OfficialNavigation.module.css";

const officialLinks: Array<{ href: string; label: string; sections: string[] }> = [
  { href: "/", label: "Overview", sections: [] },
  {
    href: "/official-forecast/revenue",
    label: "Forecasts",
    sections: ["revenue", "quantity"],
  },
  {
    href: "/official-forecast/brands",
    label: "Drivers & PLC",
    sections: ["brands", "wholesale", "plc", "top-movers"],
  },
  {
    href: "/official-forecast/governance",
    label: "Governance & QA",
    sections: ["governance"],
  },
  {
    href: "/official-forecast/output",
    label: "Output Center",
    sections: ["output"],
  },
];

export default function OfficialNavigation({ query = {} }: { query?: OfficialQuery }) {
  const pathname = usePathname();

  return (
    <header className={styles.shell}>
      <div className={styles.topline}>
        <Link href={officialHref("/", query)} className={styles.brand}>
          <span className={styles.brandMark}>PIO</span>
          <span>
            <strong>Demand Intelligence</strong>
            <small>Governed planning view</small>
          </span>
        </Link>
        <div className={styles.topActions}>
          <Link
            href="/official-forecast/update"
            className={`${styles.updateLink} ${pathname === "/official-forecast/update" ? styles.activeAction : ""}`}
          >
            <CloudUploadOutlined /> Update Forecast
            <small>Protected</small>
          </Link>
          <Link href="/data-workspace" className={styles.workspaceLink}>
            <DatabaseOutlined /> Data Workspace
            <small>Exploratory</small>
          </Link>
        </div>
      </div>
      <nav className={styles.navigation} aria-label="Official Forecast navigation">
        {officialLinks.map((link) => {
          const section = pathname.split("/").filter(Boolean).at(-1) ?? "";
          const active = link.href === "/"
            ? pathname === "/"
            : link.sections.includes(section);
          return (
            <Link
              href={officialHref(link.href, query)}
              className={active ? styles.activeNav : undefined}
              aria-current={active ? "page" : undefined}
              key={link.href}
            >
              {link.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
