import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Permite uma compilação de validação isolada sem interferir no servidor local.
  ...(process.env.NEXT_DIST_DIR ? { distDir: process.env.NEXT_DIST_DIR } : {}),
  async rewrites() {
    const apiInternalHostPort = process.env.API_INTERNAL_HOSTPORT;
    if (!apiInternalHostPort) return [];
    return [
      {
        source: "/api/:path*",
        destination: `http://${apiInternalHostPort}/:path*`,
      },
    ];
  },
};

export default nextConfig;
