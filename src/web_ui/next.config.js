// import type { NextConfig } from "next";

const nextConfig = {
  output: "export",
  // The API URL will be hardcoded to relative path for static export
  // or injected via environment variable if hosted separately
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "",
  },
  images: {
    unoptimized: true, // Required for static export
  },
};

module.exports = nextConfig;
