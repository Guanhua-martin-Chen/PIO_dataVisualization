/** @type {import('next').NextConfig} */
const backendTarget = process.env.API_PROXY_TARGET?.trim() || "http://127.0.0.1:8000";

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendTarget}/api/:path*`,
      },
      {
        source: "/docs",
        destination: `${backendTarget}/docs`,
      },
      {
        source: "/docs/:path*",
        destination: `${backendTarget}/docs/:path*`,
      },
      {
        source: "/openapi.json",
        destination: `${backendTarget}/openapi.json`,
      },
      {
        source: "/redoc",
        destination: `${backendTarget}/redoc`,
      },
    ];
  },
};

export default nextConfig;
