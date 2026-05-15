import type { NextConfig } from "next";

import { getBackendUrl } from "./src/lib/utils/backend-url";

const BACKEND_URL = getBackendUrl();

const nextConfig: NextConfig = {
  turbopack: { root: __dirname },
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
