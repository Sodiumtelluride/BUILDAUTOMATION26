import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";

export default function Home() {
  return (
    <main className="min-h-dvh bg-black px-6 py-8 text-white sm:px-10">
      <div className="mx-auto max-w-5xl">
        <header className="border-b border-white/15 pb-6 text-xl font-black tracking-tight">BUILD<span className="text-[#FF7A6E]">.</span></header>
        <div className="max-w-2xl py-16 sm:py-24">
          <p className="mb-5 text-sm font-semibold uppercase tracking-widest text-[#FF7A6E]">BUILD UMass · Website projects</p>
          <h1 className="text-5xl font-black leading-tight tracking-tight sm:text-7xl">Your next website starts here.</h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-gray-300">Tell us about your organization, your audience, and what you want to build. Our team will review your project and help with the next steps.</p>
          <Link href="/intake" className="mt-8 inline-flex min-h-12 items-center gap-3 rounded-full bg-[#DC4436] px-6 py-3 font-semibold transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white">Start your project <ArrowRight size={20} aria-hidden="true" /></Link>
          <ul className="mt-12 space-y-4 text-sm text-gray-300">
            {["Six guided sections, from goals to technical details", "Bring your ideas, branding, and any existing content", "Review your answers before sending them to BUILD"].map((text) => (
              <li key={text} className="flex items-start gap-3"><Check size={18} className="shrink-0 text-[#FF7A6E]" aria-hidden="true" />{text}</li>
            ))}
          </ul>
        </div>
      </div>
    </main>
  );
}
