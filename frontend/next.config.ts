import type { NextConfig } from "next";

const api_internal_base_url =
  process.env.API_INTERNAL_BASE_URL ?? "http://127.0.0.1:8000";

const next_config: NextConfig = {
  async rewrites() {
    return [
      {
        destination: `${api_internal_base_url}/api/:path*`,
        source: "/api/:path*",
      },
    ];
  },
};

export default next_config;
