import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
