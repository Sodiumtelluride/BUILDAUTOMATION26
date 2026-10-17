import { auth } from "@/src/auth"
import type { NextAuthRequest } from "next-auth"
import { isPublicRequest } from "@/src/lib/auth/access"
import { NextResponse, type NextRequest, type NextFetchEvent, type NextMiddleware } from "next/server"

const authenticatedProxy: (request: NextAuthRequest, event: NextFetchEvent) => ReturnType<NextMiddleware> = (req) => {
  const { pathname } = req.nextUrl
  const session = req.auth

  if (!session?.user) {
    if (pathname.startsWith("/api/")) {
      return NextResponse.json({ success: false, error: "Authentication required." }, { status: 401 })
    }
    const signInUrl = new URL("/api/auth/signin", req.nextUrl)
    signInUrl.searchParams.set("callbackUrl", req.nextUrl.href)
    return NextResponse.redirect(signInUrl)
  }

  return NextResponse.next()
}

const requireSession = auth(authenticatedProxy)

export default function proxy(req: NextRequest, event: NextFetchEvent) {
  if (isPublicRequest(req.nextUrl.pathname, req.method)) return NextResponse.next()
  return requireSession(req, event)
}

export const config = {
  matcher: ["/((?!api/auth|_next/static|_next/image|favicon\\.ico).*)"],
}
