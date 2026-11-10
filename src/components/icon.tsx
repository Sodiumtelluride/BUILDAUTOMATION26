import type { ReactNode } from "react"

/** Shared size and stroke for line icons; pass the icon's SVG paths (from lucide) as children. */
export default function Icon({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="h-4 w-4 shrink-0">
      {children}
    </svg>
  )
}
