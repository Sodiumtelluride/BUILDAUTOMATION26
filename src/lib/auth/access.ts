// Every signed-in BUILD member can open the admin console
export const CLUB_ROLES = ["admin", "reviewer", "member"]

export function isPublicRequest(pathname: string, method: string): boolean {
  if (pathname === "/api/intake" && method === "POST") return true;
  return ["/", "/login", "/signup", "/intake"].some(
    (path) => pathname === path || (path !== "/" && pathname.startsWith(`${path}/`)),
  );
}
