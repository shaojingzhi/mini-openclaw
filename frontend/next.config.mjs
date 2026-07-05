/** @type {import('next').NextConfig} */
const nextConfig = {
  allowedDevOrigins: ["http://127.0.0.1:3000", "http://localhost:3000"],
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
