import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Repo root, so web/ can import the shared fixtures in ../contracts.
  turbopack: {
    root: path.join(__dirname, ".."),
  },
  // The dev badge sits bottom-left, on top of the sidebar rail.
  devIndicators: false,
};

export default nextConfig;
