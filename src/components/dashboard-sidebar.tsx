"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import Icon from "@/src/components/icon"

// Sidebar sections. href: null = page not built yet (shown greyed out with a "Soon" tag)
const SECTIONS = [
  {
    title: "Workspace",
    items: [
      {
        label: "Dashboard",
        href: "/dashboard",
        icon: (
          <>
            <rect width="7" height="9" x="3" y="3" rx="1" />
            <rect width="7" height="5" x="14" y="3" rx="1" />
            <rect width="7" height="9" x="14" y="12" rx="1" />
            <rect width="7" height="5" x="3" y="16" rx="1" />
          </>
        ),
      },
      {
        label: "Projects",
        href: "/factory",
        icon: (
          <>
            <rect width="14" height="14" x="8" y="8" rx="2" />
            <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
          </>
        ),
      },
      {
        label: "Intakes",
        href: "/intakes",
        icon: (
          <>
            <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
            <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
          </>
        ),
      },
    ],
  },
  {
    title: "Settings",
    items: [
      {
        label: "Team",
        href: null,
        icon: (
          <>
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" />
          </>
        ),
      },
    ],
  },
]

/** Up to two initials for the avatar, e.g. "Arav Deb" -> "AD". */
function initials(nameOrEmail: string) {
  return nameOrEmail
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join("")
}

/**
 * Admin console sidebar: BUILD logo, page links, and the signed-in user with a sign-out button.
 * signOutAction: the server-side sign-out (see app/(dashboard)/dashboard/page.tsx).
 */
export default function DashboardSidebar({
  user,
  signOutAction,
}: {
  user: { name: string; email: string }
  signOutAction: () => Promise<void>
}) {
  // current URL, used to highlight the page you're on
  const pathname = usePathname()

  return (
    <aside className="flex w-full shrink-0 flex-col border-b border-white/10 md:sticky md:top-0 md:h-dvh md:w-64 md:border-b-0 md:border-r">
      <div className="flex items-center gap-3 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-linear-to-br from-[#e8314f] to-[#2a1733] text-sm font-bold">B</div>
        <span className="font-semibold">BUILD Automation</span>
      </div>

      <nav className="flex-1 space-y-6 px-3 pb-4">
        {SECTIONS.map((section) => (
          <div key={section.title}>
            <p className="px-3 pb-2 text-[11px] font-medium uppercase tracking-wider text-zinc-500">{section.title}</p>
            <ul className="space-y-1">
              {section.items.map((item) => {
                const itemStyle = "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium"
                if (!item.href) {
                  return (
                    <li key={item.label}>
                      <span aria-disabled="true" className={`${itemStyle} cursor-not-allowed text-zinc-600`}>
                        <Icon>{item.icon}</Icon>
                        {item.label}
                        <span className="ml-auto rounded-md bg-white/5 px-1.5 py-0.5 text-[10px] text-zinc-500">Soon</span>
                      </span>
                    </li>
                  )
                }
                const isActive = pathname === item.href || pathname.startsWith(item.href + "/")
                return (
                  <li key={item.label}>
                    <Link
                      href={item.href}
                      aria-current={isActive ? "page" : undefined}
                      className={`${itemStyle} transition-colors ${
                        isActive ? "bg-white/5 text-zinc-100" : "text-zinc-400 hover:bg-white/5 hover:text-zinc-100"
                      }`}
                    >
                      <Icon>{item.icon}</Icon>
                      {item.label}
                    </Link>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="flex items-center gap-3 border-t border-white/10 p-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-xs font-medium">
          {initials(user.name || user.email)}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{user.name || user.email}</p>
          <p className="truncate text-xs text-zinc-500">{user.email}</p>
        </div>
        <form action={signOutAction}>
          <button
            type="submit"
            aria-label="Sign out"
            title="Sign out"
            className="rounded-md p-1.5 text-zinc-500 transition-colors hover:bg-white/5 hover:text-zinc-100"
          >
            <Icon>
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" x2="9" y1="12" y2="12" />
            </Icon>
          </button>
        </form>
      </div>
    </aside>
  )
}
