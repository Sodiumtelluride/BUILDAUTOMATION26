export function isPublicRequest(pathname: string, method: string): boolean {
  if (pathname === "/api/intake" && method === "POST") return true;
  // Submitters have no account; the status lookup returns no personal data.
  if (method === "GET" && /^\/api\/intake\/status\/[^/]+$/.test(pathname)) return true;
  return ["/", "/login", "/signup", "/intake"].some(
    (path) => pathname === path || (path !== "/" && pathname.startsWith(`${path}/`)),
  );
}
