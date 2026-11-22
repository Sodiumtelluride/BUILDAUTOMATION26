"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";

// The frame every intake screen shares (form, status, design picker), so the
// journey after "Submit" looks like the same product as the form itself.

export function IntakeHeader({ subtitle, badge }: { subtitle: string; badge?: string }) {
  return (
    <header className="mb-8 flex items-center justify-between gap-4 border-b border-white/15 pb-5">
      <Link href="/" className="rounded text-xl font-black tracking-tight text-white focus-visible:outline-2 focus-visible:outline-white">
        BUILD<span className="text-[#FF7A6E]">.</span>
      </Link>
      <span className="flex items-center gap-2 text-sm text-gray-400">
        {badge && <span className="rounded-full border border-amber-300/40 px-2 py-0.5 text-xs font-semibold text-amber-200">{badge}</span>}
        {subtitle}
      </span>
    </header>
  );
}

export function IntakeShell({
  subtitle,
  badge,
  wide = false,
  bottomBar = false,
  children,
}: {
  subtitle: string;
  badge?: string;
  wide?: boolean;
  /** Leave room for a fixed bottom action bar. */
  bottomBar?: boolean;
  children: React.ReactNode;
}) {
  return (
    <main className={`min-h-dvh bg-black px-4 pt-6 sm:px-6 sm:pt-10 ${bottomBar ? "pb-40 sm:pb-32" : "pb-10"}`}>
      <div className={`mx-auto w-full ${wide ? "max-w-6xl" : "max-w-xl"}`}>
        <IntakeHeader subtitle={subtitle} badge={badge} />
        {children}
      </div>
    </main>
  );
}

/** Small line above the heading, like the form's "Step 2 of 6". */
export function Eyebrow({ children }: { children: React.ReactNode }) {
  return <p className="mb-2 text-sm text-gray-400">{children}</p>;
}

/** Same heading treatment as the form. Focuses once when it first appears. */
export function IntakeHeading({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  return (
    <h1 ref={ref} tabIndex={-1} className="mb-2 text-3xl font-black leading-tight tracking-tight text-white outline-none sm:text-4xl">
      {children}
    </h1>
  );
}

/** The form's section card. */
export function IntakeCard({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`rounded-2xl bg-[#1e1e1e] px-4 py-6 sm:px-6 ${className}`}>{children}</div>;
}

export function ReferenceFooter({ referenceNo, note }: { referenceNo: string; note?: string }) {
  return (
    <div className="mt-6 text-sm text-gray-400">
      <p>
        Reference number <span className="font-mono text-gray-200">{referenceNo}</span>
      </p>
      {note && <p className="mt-1 leading-relaxed">{note}</p>}
    </div>
  );
}
