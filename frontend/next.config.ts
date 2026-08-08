import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    optimizePackageImports: ["@chakra-ui/react"],
  },
  async redirects() {
    // The landing page moved from /landing to /; the app moved from / to /app.
    return [{ source: "/landing", destination: "/", permanent: false }];
  },
};

export default nextConfig;
