/**
 * Where to land after signing in.
 *
 * `?next=` is honoured ONLY when it is a path on this site. An absolute URL
 * would make the login page an OPEN REDIRECT: a link to
 * `/login?next=https://evil.example` sends someone who has just typed their
 * password to a page that can look exactly like ours and ask for it again.
 *
 * `//host` is rejected too — protocol-relative URLs are absolute, and the
 * single-slash check alone would wave them through.
 *
 * Extracted from the form so it can be tested as the pure function it is; the
 * hazard is one wrong character wide.
 */
export function destinationFor(next: string | null): string {
  if (!next) return "/";
  if (!next.startsWith("/")) return "/";
  if (next.startsWith("//")) return "/";
  return next;
}
