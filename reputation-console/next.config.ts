import type { NextConfig } from "next";
import path from "node:path";

// On a single-port host (e.g. Replit) the browser can only reach one origin, so the
// console proxies API calls to the local FastAPI backend. The console fetches `/api/*`
// (set NEXT_PUBLIC_API_BASE_URL=/api) and Next forwards it to API_PROXY_TARGET, stripping
// the /api prefix. Because it's same-origin, the httpOnly session cookie + CSRF just work
// (no CORS). In a normal split deployment, point NEXT_PUBLIC_API_BASE_URL straight at the
// API and this rewrite is simply never exercised.
// Normalize the target: trim stray whitespace/newlines (env-var tooling can introduce them) and
// ensure a scheme, so the rewrite destination is always valid (Next rejects a scheme-less target).
const _rawTarget = (process.env.API_PROXY_TARGET || "http://127.0.0.1:8000").trim();
const API_PROXY_TARGET = /^https?:\/\//i.test(_rawTarget) ? _rawTarget : `https://${_rawTarget}`;

const nextConfig: NextConfig = {
  // Pin the workspace root so Next doesn't pick a stray lockfile higher up the tree.
  turbopack: { root: path.resolve(__dirname) },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_PROXY_TARGET}/:path*` }];
  },
  async redirects() {
    // "Recommendations" is retired -- every gap-derived task now lands directly on the task
    // board (no manual promote step), so the separate recommendations inbox no longer exists.
    return [{ source: "/next-steps", destination: "/content/work-orders", permanent: false }];
  },
};

export default nextConfig;
