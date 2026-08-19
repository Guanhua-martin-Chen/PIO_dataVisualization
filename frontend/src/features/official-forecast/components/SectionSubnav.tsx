"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { officialHref, type OfficialQuery } from "../officialQuery";
import styles from "./OfficialUi.module.css";

const groups = {
  forecasts: [
    { href: "/official-forecast/revenue", label: "Revenue" },
    { href: "/official-forecast/quantity", label: "Quantity" },
  ],
  drivers: [
    { href: "/official-forecast/brands", label: "Brand Performance" },
    { href: "/official-forecast/wholesale", label: "Wholesale Inputs" },
    { href: "/official-forecast/plc", label: "Model & PLC Planning" },
    { href: "/official-forecast/top-movers", label: "Top Movers" },
  ],
} as const;

export default function SectionSubnav({ group, query = {} }: { group: keyof typeof groups; query?: OfficialQuery }) {
  const pathname = usePathname();
  return (
    <nav className={styles.subnav} aria-label={`${group} section navigation`}>
      {groups[group].map((link) => (
        <Link
          href={officialHref(link.href, query)}
          key={link.href}
          className={pathname === link.href ? styles.active : undefined}
          aria-current={pathname === link.href ? "page" : undefined}
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
