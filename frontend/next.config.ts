import type { NextConfig } from "next";

/**
 * The API is reached at `/api/*` and proxied here — it is never contacted from
 * the browser directly (multi-user.md D-2).
 *
 * WHY: the auth cookie is then FIRST-PARTY. Same origin means `SameSite=Lax`
 * behaves, CSRF has no cross-site case to exploit, and CORS stops being
 * load-bearing for the app's own requests. The alternative — the browser
 * calling :8000 across an origin — needs `credentials: "include"`, an exact
 * origin allow-list, and correct cookie attributes all holding at once, in
 * production, forever.
 *
 * `API_ORIGIN` is read by the Next SERVER at request time, not baked into the
 * browser bundle the way `NEXT_PUBLIC_API_URL` was. The API's address stops
 * being public information.
 */
const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/:path*` }];
  },
  /**
   * Where the build cache lives. `.next` unless `NEXT_DIST_DIR` says otherwise.
   *
   * Two dev servers on this repo at once — a second agent, or a second port for
   * a side-by-side check — share `.next` and quietly corrupt each other's view
   * of it. Observed twice: one server served a chunk with `NEXT_PUBLIC_API_URL`
   * baked in from the other's environment, and later a server kept serving a
   * stale chunk for minutes after the source had changed, so a verified fix
   * looked like it had not landed.
   *
   * Neither failure announces itself. The page renders, it is simply the wrong
   * page, and the natural conclusion is that the code is broken rather than the
   * cache. One env var makes the isolation available without changing anything
   * for a normal single-server run.
   */
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
