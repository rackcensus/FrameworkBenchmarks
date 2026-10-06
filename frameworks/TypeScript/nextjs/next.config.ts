import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  htmlLimitedBots: /.*/,

  async headers() {
    return [
      {
        source: "/(.*?)",
        headers: [
          { key: "Server", value: "Next.js" },
        ],
      },
    ]
  },
};

export default nextConfig;
