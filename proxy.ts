import { auth } from "@/src/auth"
import { NextResponse } from "next/server"

export default auth(function proxy(req) {
  const { pathname } = req.nextUrl
  const session = req.auth

  const publicPaths = ["/", "/login", "/signup", "/intake"]
  const isPublic = publicPaths.some(
    (p) => pathname === p || pathname.startsWith(p + "/")
  )

  if (!session && !isPublic) {
    return NextResponse.redirect(new URL("/login", req.nextUrl))
  }

  return NextResponse.next()
})

export const config = {
  matcher: ["/((?!api/auth|_next/static|_next/image|favicon\\.ico).*)"],
}
