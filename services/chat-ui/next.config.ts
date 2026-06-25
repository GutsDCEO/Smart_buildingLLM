import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for multi-stage Docker build (runner stage uses server.js)
  output: "standalone",

  // Disable in-memory caching in Next.js to significantly reduce development server RAM usage
  cacheMaxMemorySize: 0,

  // ── API Proxy — Eliminates CORS issues permanently ──────────────────────
  // The browser calls /api/backend/... (same origin → CORS never triggered).
  // Next.js Node.js server then forwards the request to FastAPI internally.
  // BACKEND_URL is a server-side-only env var — it is never baked into the
  // client bundle, so the app works from any device on any network without
  // any .env changes before a demo.
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8003";
    return [
      {
        source: "/api/backend/:path*",
        destination: `${backendUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
