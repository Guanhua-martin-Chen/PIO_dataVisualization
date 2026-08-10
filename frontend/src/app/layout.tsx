import type { Metadata } from "next";
import { ConfigProvider } from "antd";
import "antd/dist/reset.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "PIO Demand Intelligence Platform",
  description: "Governed PIO forecast overview and exploratory data workspace.",
};

const theme = {
  token: {
    colorPrimary: "#2054f4",
    colorText: "#122033",
    colorTextSecondary: "#64748b",
    colorBgBase: "#f3f6fb",
    colorBorderSecondary: "#dbe4ef",
    borderRadius: 18,
    fontFamily: '"IBM Plex Sans", sans-serif',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <ConfigProvider theme={theme}>{children}</ConfigProvider>
      </body>
    </html>
  );
}
