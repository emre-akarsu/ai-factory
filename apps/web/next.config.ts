import type { NextConfig } from "next";

const api = process.env.FACTORY_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // The browser only talks to this app; store calls and media are proxied to the Python API.
  async rewrites() {
    return [
      { source: "/api/store/:path*", destination: `${api}/v1/store/:path*` },
      { source: "/media/:employee/:path*", destination: `${api}/v1/store/assets/:employee/:path*` },
    ];
  },
};

export default nextConfig;
