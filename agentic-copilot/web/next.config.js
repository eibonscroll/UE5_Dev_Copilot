/** @type {import('next').NextConfig} */
const nextConfig = {
  // needed if your Dockerfile copies .next/standalone and runs `node server.js`
  output: 'standalone',

  reactStrictMode: true,

  // keep the proxy so the browser hits /api and Next forwards it to the Python API
  async rewrites() {
    return [
      { source: '/api/:path*', destination: 'http://app:8080/:path*' },
      { source: "/download/:path*", destination: "http://app:8080/download/:path*" },
    ];
  },

  // optional, but can avoid surprises in containers
  images: { unoptimized: true },
};

module.exports = nextConfig;
