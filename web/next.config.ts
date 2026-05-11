import type { NextConfig } from "next";

const internalApiUrl = process.env.INTERNAL_API_URL ?? "http://api:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${internalApiUrl}/api/:path*`
      },
      {
        source: "/health",
        destination: `${internalApiUrl}/health`
      }
    ];
  }
};

export default nextConfig;
