import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Six files at 10MB each, plus multipart headers and the project answers.
  // The route also enforces this limit while reading the request stream.
  experimental: { proxyClientMaxBodySize: "64mb" },
};

export default nextConfig;
