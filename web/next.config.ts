import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Repo root, so web/ can import the shared fixtures in ../contracts.
  turbopack: {
    root: path.join(__dirname, ".."),
  },
  // The dev badge sits bottom-left, on top of the sidebar rail.
  devIndicators: false,
  // Next 16 treats each dev host as a separate origin and blocks /_next/hmr from
  // any it was not told about. Without this, opening the app on 127.0.0.1 (or the
  // LAN IP, on a phone) loads the server-rendered HTML but never connects the
  // Turbopack runtime, so the page hydrates never and sits on "Loading workspace…".
  allowedDevOrigins: ["localhost", "127.0.0.1", "[::1]"],
};

export default nextConfig;
