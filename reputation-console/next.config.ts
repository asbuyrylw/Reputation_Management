import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // Pin the workspace root so Next doesn't pick a stray lockfile higher up the tree.
  turbopack: { root: path.resolve(__dirname) },
};

export default nextConfig;
