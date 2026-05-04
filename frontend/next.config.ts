import type { NextConfig } from "next";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\\n$/, "").replace(/\n$/, "") ||
  "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        // Proxy all API calls to the backend (avoids CORS issues)
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
