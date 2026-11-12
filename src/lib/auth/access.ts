export function isPublicRequest(pathname: string, method: string): boolean {
  if (pathname === "/api/intake" && method === "POST") return true;
  return ["/", "/login", "/signup", "/intake"].some(
    (path) => pathname === path || (path !== "/" && pathname.startsWith(`${path}/`)),
  );
}
