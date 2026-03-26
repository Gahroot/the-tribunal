import type { NextConfig } from "next";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\\n$/, "").replace(/\n$/, "") ||
  "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        // Proxy public embed API calls to the backend
        source: "/api/v1/p/embed/:path*",
        destination: `${BACKEND_URL}/api/v1/p/embed/:path*`,
      },
    ];
  },
};

export default nextConfig;
