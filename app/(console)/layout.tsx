import type { ReactNode } from "react"
import { auth, signOut } from "@/src/auth"
import DashboardSidebar from "@/src/components/dashboard-sidebar"

// Runs on the server when "Sign out" is clicked
async function logout() {
  "use server"
  await signOut({ redirectTo: "/login" })
}

/**
 * Shared frame for the admin console pages (/dashboard, /factory): dark background + sidebar.
 * It only reads who is signed in to show their name. Each page still checks access itself,
 * because layouts don't re-run when you move between pages.
 */
export default async function ConsoleLayout({ children }: { children: ReactNode }) {
  const session = await auth()
  if (!session?.user) return children // signed out: "/" just redirects to /login

  return (
    <div className="flex min-h-dvh flex-col bg-zinc-950 font-sans text-zinc-100 md:flex-row">
      <DashboardSidebar user={{ name: session.user.name ?? "", email: session.user.email ?? "" }} signOutAction={logout} />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}
