const BACKEND_TARGET =
  process.env.BACKEND_INTERNAL_URL ||
  (process.env.NEXT_PUBLIC_API_BASE_URL
    ? process.env.NEXT_PUBLIC_API_BASE_URL.replace(/\/api\/v1\/?$/, "")
    : "http://localhost:8000");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${BACKEND_TARGET}/api/v1/:path*`,
      },
      {
        source: "/api/:path*",
        destination: `${BACKEND_TARGET}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
