"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Check, Circle, ExternalLink, LoaderCircle, RefreshCw, SearchX, X } from "lucide-react";
import { pollDelayMs, type PublicJobStatus, type PublicPhase, type StepState } from "@/src/lib/intake/job-status";
import { fetchJobStatus } from "./job-status-client";

const MAX_RETRY_DELAY_MS = 60_000;

const COPY: Record<PublicPhase, { title: string; body: string }> = {
  queued: {
    title: "Your project is in line.",
    body: "We've received your answers. Your site will start building in a moment.",
  },
  generating: {
    title: "We're building your site.",
    body: "This usually takes a few minutes. You can keep this page open or come back later. This link always shows your latest status.",
  },
  in_review: {
    title: "Your draft is with the BUILD team.",
    body: "A BUILD team member checks every site before anything goes live. We'll email you when it's ready. You don't need to keep this page open.",
  },
  publishing: {
    title: "Approved. Publishing now.",
    body: "Your site passed review and is being published. Your link will appear here and in your email.",
  },
  live: {
    title: "Your website is live.",
    body: "Thanks for working with BUILD UMass. We've also emailed you this link.",
  },
  failed: {
    title: "We hit a problem building your site.",
    body: "The BUILD team has been notified and will follow up by email. Please don't submit the form again. If you have questions, reply to your confirmation email and include your reference number.",
  },
};

type ViewState =
  | { kind: "loading" }
  | { kind: "ready"; data: PublicJobStatus }
  | { kind: "not_found" }
  | { kind: "unavailable" };

function StepIcon({ state }: { state: StepState }) {
  if (state === "done") {
    return (
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#DC4436]">
        <Check size={16} className="text-white" aria-hidden="true" />
      </span>
    );
  }
  if (state === "active") {
    return (
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 border-[#DC4436]">
        <LoaderCircle size={16} className="text-white motion-safe:animate-spin" aria-hidden="true" />
      </span>
    );
  }
  if (state === "failed") {
    return (
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white/10 ring-2 ring-[#DC4436]">
        <X size={16} className="text-[#ff8a7f]" aria-hidden="true" />
      </span>
    );
  }
  return (
    <span className="flex h-7 w-7 shrink-0 items-center justify-center">
      <Circle size={18} className="text-white/25" aria-hidden="true" />
    </span>
  );
}

const STATE_LABEL: Record<StepState, string> = { done: "done", active: "in progress", failed: "stopped", pending: "not started" };

function Steps({ steps }: { steps: PublicJobStatus["steps"] }) {
  const done = steps.filter((s) => s.state === "done").length;
  return (
    <div className="mt-10 w-full max-w-md text-left">
      <div className="mb-5 h-1.5 w-full overflow-hidden rounded-full bg-white/10" role="progressbar" aria-label="Website progress" aria-valuemin={0} aria-valuemax={steps.length} aria-valuenow={done}>
        <div className="h-full rounded-full bg-[#DC4436] transition-[width] duration-700 ease-out" style={{ width: `${(done / steps.length) * 100}%` }} />
      </div>
      <ol className="space-y-3">
        {steps.map((step) => (
          <li key={step.key} className="flex items-center gap-3">
            <StepIcon state={step.state} />
            <span className={step.state === "pending" ? "text-sm text-gray-500" : step.state === "active" ? "text-sm font-semibold text-white" : "text-sm text-gray-200"}>
              {step.label}
              <span className="sr-only">: {STATE_LABEL[step.state]}</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function Shell({ referenceNo, children }: { referenceNo: string; children: React.ReactNode }) {
  return (
    <main className="min-h-dvh bg-black flex flex-col items-center px-6 py-16 text-center sm:justify-center">
      {children}
      <div className="mt-12 flex flex-col items-center">
        <p className="text-sm text-gray-400">Your reference number</p>
        <p className="mt-2 rounded-xl border border-white/20 px-5 py-3 font-mono text-lg text-white">{referenceNo}</p>
        <p className="mt-4 max-w-sm text-sm leading-relaxed text-gray-400">Bookmark this page to check back anytime. We&apos;ll send updates to the email address you gave us.</p>
        <Link href="/" className="mt-6 min-h-11 rounded-full px-5 py-3 text-sm font-semibold text-white underline underline-offset-4 hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-white">Back to BUILD</Link>
      </div>
    </main>
  );
}

// Focuses once when it first appears (so screen readers land on it); later
// phase changes are announced by the aria-live region instead.
function Heading({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  return <h1 tabIndex={-1} ref={ref} className="text-4xl sm:text-5xl font-black text-white mb-4 tracking-tight outline-none">{children}</h1>;
}

export function JobStatusView({ referenceNo }: { referenceNo: string }) {
  const [view, setView] = useState<ViewState>({ kind: "loading" });
  const [reconnecting, setReconnecting] = useState(false);
  // Bumped by "Try again" to restart the polling loop from scratch.
  const [runId, setRunId] = useState(0);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    let controller: AbortController | null = null;
    let failures = 0;
    let phase: PublicPhase | null = null;
    let stopped = false;
    let disposed = false;

    const check = async () => {
      if (timer) clearTimeout(timer);
      controller?.abort();
      const abort = new AbortController();
      controller = abort;

      let nextDelay: number | null;
      try {
        const result = await fetchJobStatus(referenceNo, abort.signal);
        if (disposed) return;
        if (result.kind === "ok") {
          failures = 0;
          phase = result.data.phase;
          setReconnecting(false);
          setView({ kind: "ready", data: result.data });
          nextDelay = pollDelayMs(phase);
        } else if (result.kind === "not_found") {
          setView({ kind: "not_found" });
          nextDelay = null;
        } else {
          // Keep the last known status on screen; back off so a blip doesn't hammer the API.
          failures += 1;
          setReconnecting(true);
          setView((prev) => (prev.kind === "loading" ? { kind: "unavailable" } : prev));
          nextDelay = Math.min((pollDelayMs(phase) ?? 5_000) * 2 ** failures, MAX_RETRY_DELAY_MS);
        }
      } catch {
        return; // aborted by a newer check or by unmount
      }

      if (nextDelay === null) stopped = true;
      else if (!document.hidden) timer = setTimeout(check, nextDelay);
    };

    // Pause while the tab is hidden; check right away when the person comes back.
    const onVisibility = () => {
      if (document.hidden) {
        if (timer) clearTimeout(timer);
      } else if (!stopped) {
        check();
      }
    };

    check();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      disposed = true;
      document.removeEventListener("visibilitychange", onVisibility);
      if (timer) clearTimeout(timer);
      controller?.abort();
    };
  }, [referenceNo, runId]);

  const retry = () => {
    setView((prev) => (prev.kind === "unavailable" ? { kind: "loading" } : prev));
    setRunId((n) => n + 1);
  };

  if (view.kind === "loading") {
    return (
      <Shell referenceNo={referenceNo}>
        <LoaderCircle size={40} className="mb-8 text-white motion-safe:animate-spin" aria-hidden="true" />
        <p className="text-gray-300" role="status">Checking on your project…</p>
      </Shell>
    );
  }

  if (view.kind === "not_found") {
    return (
      <Shell referenceNo={referenceNo}>
        <div className="mb-8 flex h-20 w-20 items-center justify-center rounded-full bg-white/10">
          <SearchX size={36} className="text-white" aria-hidden="true" />
        </div>
        <Heading>We couldn&apos;t find that project.</Heading>
        <p className="max-w-sm text-base leading-relaxed text-gray-300">Check that the link matches the one in your confirmation email. If you just submitted, wait a moment and refresh.</p>
      </Shell>
    );
  }

  if (view.kind === "unavailable") {
    return (
      <Shell referenceNo={referenceNo}>
        <div className="mb-8 flex h-20 w-20 items-center justify-center rounded-full bg-white/10">
          <AlertTriangle size={36} className="text-white" aria-hidden="true" />
        </div>
        <Heading>We can&apos;t load your status right now.</Heading>
        <p className="max-w-sm text-base leading-relaxed text-gray-300">Your project was received and is safe. We&apos;ll keep trying in the background.</p>
        <button type="button" onClick={retry} className="mt-6 inline-flex min-h-11 items-center gap-2 rounded-full bg-white px-5 py-3 text-sm font-semibold text-black hover:bg-gray-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white">
          <RefreshCw size={16} aria-hidden="true" /> Try again
        </button>
      </Shell>
    );
  }

  const { data } = view;
  const copy = COPY[data.phase];
  return (
    <Shell referenceNo={referenceNo}>
      <div className={`mb-8 flex h-20 w-20 items-center justify-center rounded-full ${data.phase === "failed" ? "bg-white/10" : "bg-[#DC4436]"}`}>
        {data.phase === "live" ? <Check size={40} className="text-white" aria-hidden="true" />
          : data.phase === "failed" ? <AlertTriangle size={36} className="text-white" aria-hidden="true" />
          : <LoaderCircle size={40} className="text-white motion-safe:animate-spin [animation-duration:2s]" aria-hidden="true" />}
      </div>
      <div aria-live="polite" className="flex flex-col items-center">
        <Heading>{copy.title}</Heading>
        <p className="max-w-md text-base leading-relaxed text-gray-300">{copy.body}</p>
      </div>

      {data.phase === "live" && data.liveUrl && (
        <div className="mt-8 flex flex-col items-center gap-3">
          <a href={data.liveUrl} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-12 items-center gap-2 rounded-full bg-[#DC4436] px-6 py-3 text-base font-semibold text-white hover:bg-[#c43a2d] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white">
            Visit your website <ExternalLink size={18} aria-hidden="true" />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
          <p className="max-w-full font-mono text-sm text-gray-400 [overflow-wrap:anywhere]">{data.liveUrl.replace(/^https?:\/\//, "").replace(/\/$/, "")}</p>
        </div>
      )}

      {data.phase !== "live" && <Steps steps={data.steps} />}

      {reconnecting && data.phase !== "live" && data.phase !== "failed" && (
        <p className="mt-6 text-xs text-gray-500" role="status">Having trouble reaching BUILD. Retrying…</p>
      )}
    </Shell>
  );
}
