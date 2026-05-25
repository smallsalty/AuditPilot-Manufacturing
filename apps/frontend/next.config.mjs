/** @type {import('next').NextConfig} */
const backendApiOrigin = process.env.BACKEND_API_ORIGIN?.replace(/\/$/, "");

const nextConfig = {
  transpilePackages: ["@auditpilot/shared-types"],
  async rewrites() {
    if (!backendApiOrigin) {
      return [];
    }

    return [
      {
        source: "/api/:path*",
        destination: `${backendApiOrigin}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
