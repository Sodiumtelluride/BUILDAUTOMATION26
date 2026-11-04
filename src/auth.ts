import NextAuth from "next-auth"
import Credentials from "next-auth/providers/credentials"
import bcrypt from "bcryptjs"
import { eq } from "drizzle-orm"
import { getDb } from "@/src/db"
import { users } from "@/src/db/schema"
import type { UserRole } from "@/src/types/next-auth"

export const { handlers, auth, signIn, signOut } = NextAuth({
  // Credentials users are queried in authorize; JWT sessions need no adapter.
  // Credentials provider requires JWT strategy; database strategy doesn't support it
  session: { strategy: "jwt" },
  providers: [
    Credentials({
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (typeof credentials?.email !== "string" || typeof credentials?.password !== "string" || !credentials.email.trim() || !credentials.password) return null
        const user = await getDb().query.users.findFirst({
          where: eq(users.email, credentials.email.trim().toLowerCase()),
        })
        if (!user?.passwordHash) return null
        const valid = await bcrypt.compare(credentials.password, user.passwordHash)
        if (!valid) return null
        return { id: user.id, email: user.email, name: user.name, role: user.role }
      },
    }),
  ],
  secret: process.env.AUTH_SECRET,
  callbacks: {
    jwt({ token, user }) {
      if (user) token.role = (user as { role: UserRole }).role
      return token
    },
    session({ session, token }) {
      session.user.role = token.role === "admin" || token.role === "reviewer" ? token.role : "member"
      return session
    },
  },
})
