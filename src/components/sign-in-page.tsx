"use client"

import Link from "next/link"
import { useState } from "react"

// Shared look for the text boxes; turns violet when focused
const inputStyle =
  "w-full rounded-2xl border border-zinc-800 bg-white/5 p-4 text-sm placeholder:text-zinc-500 transition-colors focus:border-violet-400/70 focus:bg-violet-500/10 focus:outline-none"

/** Open-eye icon (from lucide), shown while the password is hidden. */
function EyeIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
      <path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

/** Crossed-out eye icon (from lucide), shown while the password is visible. */
function EyeOffIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
      <path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49" />
      <path d="M14.084 14.158a3 3 0 0 1-4.242-4.242" />
      <path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143" />
      <path d="m2 2 20 20" />
    </svg>
  )
}

/**
 * BUILD Automation slide art (red-to-plum gradient with waves), turned 90° to fit a tall panel.
 * "slice" makes it fill the box; "YMax" crops from the top so the waves at the bottom stay visible.
 */
function BuildWaveArt() {
  return (
    <svg viewBox="0 0 617 1080" preserveAspectRatio="xMidYMax slice" aria-hidden="true" className="h-full w-full">
      <defs>
        <linearGradient id="build-bg" x1="1" y1="0" x2="0.15" y2="0.8">
          <stop offset="0" stopColor="#e8314f" />
          <stop offset="0.45" stopColor="#7d1d42" />
          <stop offset="0.8" stopColor="#2a1733" />
          <stop offset="1" stopColor="#1e1530" />
        </linearGradient>
        <linearGradient id="build-wave" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#e3304d" />
          <stop offset="1" stopColor="#b8213f" />
        </linearGradient>
      </defs>
      <rect width="617" height="1080" fill="url(#build-bg)" />
      {/* waves along the left edge */}
      <path d="M0,330 C40,380 80,450 105,560 C125,660 110,760 80,850 C55,930 70,1010 110,1080 L0,1080 Z" fill="url(#build-wave)" />
      <path d="M0,560 C30,640 45,730 35,820 C25,900 30,990 60,1080 L0,1080 Z" fill="#ea4058" opacity={0.6} />
      {/* waves along the bottom edge */}
      <path d="M402,1080 C395,1040 360,1000 300,985 C230,968 150,990 90,1030 C60,1050 40,1065 30,1080 Z" fill="#d42a48" opacity={0.85} />
      <path d="M617,810 C560,795 480,805 427,830 C375,858 335,915 300,975 C280,1010 255,1050 240,1080 L617,1080 Z" fill="url(#build-wave)" />
    </svg>
  )
}

/**
 * Admin console sign-in screen.
 * action: the server-side login (see app/login/page.tsx). error: true after a failed attempt.
 */
export default function SignInPage({
  action,
  error = false,
}: {
  action: (formData: FormData) => Promise<void>
  error?: boolean
}) {
  // true = show the password as plain text
  const [showPassword, setShowPassword] = useState(false)

  return (
    <main className="flex min-h-dvh flex-col bg-zinc-950 font-sans text-zinc-100 md:flex-row">
      {/* Left column: sign-in form */}
      <section className="flex flex-1 items-center justify-center p-8">
        <div className="flex w-full max-w-md flex-col gap-6">
          <h1 className="text-4xl font-light tracking-tighter md:text-5xl">Welcome back</h1>
          <p className="text-zinc-400">Sign in to the BUILD admin console</p>

          {/* action runs on the server, so the password never ends up in the URL */}
          <form className="space-y-5" action={action}>
            <div className="space-y-2">
              <label htmlFor="email" className="text-sm font-medium text-zinc-400">Email</label>
              <input id="email" name="email" type="email" autoComplete="email" required placeholder="you@umass.edu" className={inputStyle} />
            </div>

            <div className="space-y-2">
              <label htmlFor="password" className="text-sm font-medium text-zinc-400">Password</label>
              <div className="relative">
                <input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  placeholder="Enter your password"
                  className={`${inputStyle} pr-12`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="absolute inset-y-0 right-3 flex items-center text-zinc-400 transition-colors hover:text-zinc-100"
                >
                  {showPassword ? <EyeOffIcon /> : <EyeIcon />}
                </button>
              </div>
            </div>

            <label className="flex cursor-pointer items-center gap-3 text-sm text-zinc-300">
              <input type="checkbox" name="rememberMe" className="h-4 w-4 accent-violet-500" />
              Keep me signed in
            </label>

            {error && <p className="text-sm text-red-400">Wrong email or password.</p>}

            <button type="submit" className="w-full rounded-2xl bg-zinc-100 py-4 font-medium text-zinc-900 transition-colors hover:bg-zinc-300">
              Sign In
            </button>
          </form>

          <p className="text-center text-sm text-zinc-500">Forgot your password? Ask an admin to reset it.</p>
          <Link href="/" className="text-center text-sm text-zinc-400 underline underline-offset-4 transition-colors hover:text-zinc-100">
            ← Back to homepage
          </Link>
        </div>
      </section>

      {/* Right column: BUILD wave art in a rounded panel (hidden on phones) */}
      <section className="relative hidden flex-1 p-4 md:block">
        <div className="absolute inset-4 overflow-hidden rounded-3xl">
          <BuildWaveArt />
        </div>
      </section>
    </main>
  )
}
