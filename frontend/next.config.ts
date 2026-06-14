import { withSentryConfig } from "@sentry/nextjs";
import type { NextConfig } from "next";

import { getBackendUrl } from "./src/lib/utils/backend-url";

const BACKEND_URL = getBackendUrl();

const nextConfig: NextConfig = {
  serverExternalPackages: ["@prestyj/pixel"],
  turbopack: { root: __dirname },
  // Avatar image sources. Any host that may legitimately serve a user-supplied
  // avatar URL needs to be allow-listed for next/image. Add new hosts here
  // (rather than reaching for `unoptimized`) so we still get optimization +
  // CSP protection.
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "www.gravatar.com", pathname: "/avatar/**" },
      { protocol: "https", hostname: "secure.gravatar.com", pathname: "/avatar/**" },
      { protocol: "https", hostname: "gravatar.com", pathname: "/avatar/**" },
      // Google profile images (used by OAuth login flows)
      { protocol: "https", hostname: "lh3.googleusercontent.com" },
      // Generic CDN-uploaded avatars
      { protocol: "https", hostname: "avatars.githubusercontent.com" },
      { protocol: "https", hostname: "*.public.blob.vercel-storage.com" },
      { protocol: "https", hostname: "*.amazonaws.com" },
      { protocol: "https", hostname: "*.r2.cloudflarestorage.com" },
    ],
  },
  async rewrites() {
    return [
      {
        // Proxy all API calls to the backend (avoids CORS issues)
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
      {
        // Proxy public backend assets, including seeded lead-magnet PDFs.
        source: "/static/:path*",
        destination: `${BACKEND_URL}/static/:path*`,
      },
    ];
  },
};

// Sentry release + source-map upload requires a server-side auth token. When
// ``SENTRY_AUTH_TOKEN`` isn't configured (e.g. preview / local builds, or
// production envs where the token hasn't been provisioned yet) the plugin
// emits two warnings per build ("Will not create release", "Will not upload
// source maps"). Detect that here and explicitly disable the source-maps
// pipeline so the build stays warning-free until a real token is wired up.
const SENTRY_HAS_AUTH_TOKEN = Boolean(process.env.SENTRY_AUTH_TOKEN);

export default withSentryConfig(nextConfig, {
  // Only print logs for uploading source maps in CI
  silent: !process.env.CI,
  // Upload a larger set of source maps for prettier stack traces (increases build time)
  widenClientFileUpload: true,
  sourcemaps: {
    disable: !SENTRY_HAS_AUTH_TOKEN,
  },
  // Automatically tree-shake Sentry logger statements to reduce bundle size.
  // (Moved from the top-level ``disableLogger`` to the new ``webpack.treeshake``
  // path so the build no longer emits the @sentry/nextjs deprecation warning.)
  webpack: {
    treeshake: {
      removeDebugLogging: true,
    },
  },
});
