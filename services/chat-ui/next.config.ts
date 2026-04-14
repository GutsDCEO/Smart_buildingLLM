import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for multi-stage Docker build (runner stage uses server.js)
  output: "standalone",
};

export default nextConfig;
