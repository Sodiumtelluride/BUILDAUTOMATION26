"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, Check, Circle, ExternalLink, Hand, LoaderCircle, RefreshCw, X } from "lucide-react";
import { pollDelayMs, SELECTION_INDEX, type PublicJobStatus, type PublicPhase, type StepState } from "@/src/lib/intake/job-status";
import { describeFamily, designsPagePath } from "@/src/lib/intake/design-options";
import { getStatusFetcher } from "./job-status-client";
import { isIntakeMockEnabled } from "./mock-journey";
import { Eyebrow, IntakeCard, IntakeHeading, IntakeShell, ReferenceFooter } from "./IntakeShell";

const MAX_RETRY_DELAY_MS = 60_000;
/** While the tab is in the background, keep checking (slowly) so the person can be told it's their turn. */
const HIDDEN_POLL_MS = 60_000;
const READY_TITLE = "Your designs are ready · BUILD";

type ViewState =
  | { kind: "loading" }
  | { kind: "ready"; data: PublicJobStatus }
  | { kind: "not_found" }
  | { kind: "unavailable" };

function copyFor(data: PublicJobStatus): { title: string; body: string } {
  const choseDesign = data.steps[SELECTION_INDEX]?.state === "done";
  switch (data.phase) {
    case "queued":
      return { title: "Your project is in line.", body: "We've received your answers. We'll start building your design options in a moment." };
    case "generating":
      return choseDesign
        ? { title: "We're writing your content.", body: "We're filling your chosen design with your content. Next, the BUILD team reviews your site. We'll email you when it's ready, so you don't need to keep this page open." }
        : { title: "We're building your design options.", body: "This usually takes a few minutes. Next, you'll choose the design you like best, so keep this page open or bookmark it to come back." };
    case "choosing_design":
      return { title: "Your designs are ready.", body: "It's your turn: pick the look you like best, and we'll write your content into it." };
    case "in_review":
      return { title: "Your draft is with the BUILD team.", body: "A BUILD team member checks every site before anything goes live. We'll email you when it's ready. You don't need to keep this page open." };
    case "publishing":
      return { title: "Approved. Publishing now.", body: "Your site passed review and is being published. Your link will appear here and in your email." };
    case "live":
      return { title: "Your website is live.", body: "Thanks for working with BUILD UMass. We've also emailed you this link." };
    case "failed":
      return { title: "We hit a problem building your site.", body: "The BUILD team has been notified and will follow up by email. Please don't submit the form again. If you have questions, reply to your confirmation email and include your reference number." };
  }
}

function eyebrowFor(data: PublicJobStatus): string {
  const total = data.steps.length;
  const at = data.steps.findIndex((s) => s.state === "active" || s.state === "failed");
  if (data.phase === "live") return `All ${total} steps done`;
  if (data.phase === "queued" || at < 0) return `Step 1 of ${total}`;
  if (data.phase === "failed") return `Stopped at step ${at + 1} of ${total}`;
  return `Step ${at + 1} of ${total}${data.phase === "choosing_design" ? " · Your turn" : ""}`;
}

/** Same segmented bar as the form's section progress. */
function SegmentBar({ steps }: { steps: PublicJobStatus["steps"] }) {
  const done = steps.filter((s) => s.state === "done").length;
  return (
    <div className="mb-5 mt-4 grid gap-2" style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }} role="progressbar" aria-label="Website progress" aria-valuemin={0} aria-valuemax={steps.length} aria-valuenow={done}>
      {steps.map((s) => (
        <span key={s.key} className={`h-1.5 rounded-full ${s.state === "done" ? "bg-[#FF7A6E]" : s.state === "active" ? "bg-[#FF7A6E]/60 motion-safe:animate-pulse" : s.state === "failed" ? "bg-[#DC4436]" : "bg-white/25"}`} />
      ))}
    </div>
  );
}

function StepIcon({ state, yourTurn }: { state: StepState; yourTurn: boolean }) {
  const box = "flex h-7 w-7 shrink-0 items-center justify-center rounded-full";
  if (state === "done") return <span className={`${box} bg-[#DC4436]`}><Check size={16} className="text-white" aria-hidden="true" /></span>;
  if (state === "active" && yourTurn) return <span className={`${box} bg-white`}><Hand size={15} className="text-black" aria-hidden="true" /></span>;
  if (state === "active") return <span className={`${box} border-2 border-[#DC4436]`}><LoaderCircle size={16} className="text-white motion-safe:animate-spin" aria-hidden="true" /></span>;
  if (state === "failed") return <span className={`${box} bg-white/10 ring-2 ring-[#DC4436]`}><X size={16} className="text-[#ff8a7f]" aria-hidden="true" /></span>;
  return <span className={box}><Circle size={18} className="text-white/25" aria-hidden="true" /></span>;
}

const STATE_LABEL: Record<StepState, string> = { done: "done", active: "in progress", failed: "stopped", pending: "not started" };

function Steps({ steps }: { steps: PublicJobStatus["steps"] }) {
  return (
    <ol className="space-y-3">
      {steps.map((step) => {
        const yourTurn = step.key === "DESIGN_SELECTION";
        return (
          <li key={step.key} className="flex items-center gap-3">
            <StepIcon state={step.state} yourTurn={yourTurn} />
            <span className={step.state === "pending" ? "text-sm text-gray-500" : step.state === "active" ? "text-sm font-semibold text-white" : "text-sm text-gray-200"}>
              {step.label}
              {yourTurn && step.state !== "done" && <span className="ml-2 rounded-full border border-white/20 px-2 py-0.5 text-xs font-medium text-gray-300">You</span>}
              <span className="sr-only">: {yourTurn && step.state === "active" ? "your turn" : STATE_LABEL[step.state]}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

const primaryButton = "inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-[#DC4436] px-6 text-base font-semibold text-white hover:bg-[#c43a2d] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white";

export function JobStatusView({ referenceNo, chosenFamily = null }: { referenceNo: string; chosenFamily?: string | null }) {
  const [fetchStatus] = useState(getStatusFetcher);
  const [view, setView] = useState<ViewState>({ kind: "loading" });
  const [reconnecting, setReconnecting] = useState(false);
  // Bumped by "Try again" to restart the polling loop from scratch.
  const [runId, setRunId] = useState(0);
  const router = useRouter();
  const phase = view.kind === "ready" ? view.data.phase : null;
  const badge = isIntakeMockEnabled() ? "Demo data" : undefined;

  // The design picker is its own page: hand off as soon as designs are ready,
  // and flag it in the tab title for someone working in another tab.
  useEffect(() => {
    if (phase !== "choosing_design") return;
    document.title = READY_TITLE;
    router.replace(designsPagePath(referenceNo));
  }, [phase, referenceNo, router]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    let controller: AbortController | null = null;
    let failures = 0;
    let current: PublicPhase | null = null;
    let stopped = false;
    let disposed = false;

    const check = async () => {
      if (timer) clearTimeout(timer);
      controller?.abort();
      const abort = new AbortController();
      controller = abort;

      let nextDelay: number | null;
      try {
        const result = await fetchStatus(referenceNo, abort.signal);
        if (disposed) return;
        if (result.kind === "ok") {
          failures = 0;
          current = result.data.phase;
          setReconnecting(false);
          setView({ kind: "ready", data: result.data });
          nextDelay = pollDelayMs(current);
        } else if (result.kind === "not_found") {
          setView({ kind: "not_found" });
          nextDelay = null;
        } else {
          // Keep the last known status on screen; back off so a blip doesn't hammer the API.
          failures += 1;
          setReconnecting(true);
          setView((prev) => (prev.kind === "loading" ? { kind: "unavailable" } : prev));
          nextDelay = Math.min((pollDelayMs(current) ?? 5_000) * 2 ** failures, MAX_RETRY_DELAY_MS);
        }
      } catch {
        return; // aborted by a newer check or by unmount
      }

      if (nextDelay === null) stopped = true;
      else timer = setTimeout(check, document.hidden ? Math.max(nextDelay, HIDDEN_POLL_MS) : nextDelay);
    };

    // Coming back to the tab: check right away instead of waiting out a slow timer.
    const onVisibility = () => {
      if (!document.hidden && !stopped) check();
    };

    check();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      disposed = true;
      document.removeEventListener("visibilitychange", onVisibility);
      if (timer) clearTimeout(timer);
      controller?.abort();
    };
  }, [referenceNo, runId, fetchStatus]);

  const retry = () => {
    setView((prev) => (prev.kind === "unavailable" ? { kind: "loading" } : prev));
    setRunId((n) => n + 1);
  };

  const footer = <ReferenceFooter referenceNo={referenceNo} note="Bookmark this page to check back anytime. We'll send updates to the email address you gave us." />;

  if (view.kind === "loading") {
    return (
      <IntakeShell subtitle="Your website project" badge={badge}>
        <p className="flex items-center gap-3 text-gray-300" role="status">
          <LoaderCircle size={20} className="motion-safe:animate-spin" aria-hidden="true" /> Checking on your project…
        </p>
        {footer}
      </IntakeShell>
    );
  }

  if (view.kind === "not_found") {
    return (
      <IntakeShell subtitle="Your website project" badge={badge}>
        <IntakeHeading>We couldn&apos;t find that project.</IntakeHeading>
        <p className="text-sm leading-relaxed text-gray-300">Check that the link matches the one in your confirmation email. If you just submitted, wait a moment and refresh.</p>
        {footer}
      </IntakeShell>
    );
  }

  if (view.kind === "unavailable") {
    return (
      <IntakeShell subtitle="Your website project" badge={badge}>
        <IntakeHeading>We can&apos;t load your status right now.</IntakeHeading>
        <p className="text-sm leading-relaxed text-gray-300">Your project was received and is safe. We&apos;ll keep trying in the background.</p>
        <button type="button" onClick={retry} className="mt-6 inline-flex min-h-11 items-center gap-2 rounded-full bg-white px-5 text-sm font-semibold text-black hover:bg-gray-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white">
          <RefreshCw size={16} aria-hidden="true" /> Try again
        </button>
        {footer}
      </IntakeShell>
    );
  }

  const { data } = view;
  const copy = copyFor(data);
  const choseDesign = data.steps[SELECTION_INDEX]?.state === "done";

  return (
    <IntakeShell subtitle="Your website project" badge={badge}>
      <div aria-live="polite">
        <Eyebrow>{eyebrowFor(data)}</Eyebrow>
        <IntakeHeading>{copy.title}</IntakeHeading>
        <p className="text-sm leading-relaxed text-gray-300">{copy.body}</p>
      </div>

      {chosenFamily && choseDesign && data.phase !== "live" && (
        <p role="status" className="mt-5 flex items-center gap-2 rounded-xl border border-white/15 px-4 py-3 text-sm text-gray-200">
          <Check size={16} className="shrink-0 text-[#FF7A6E]" aria-hidden="true" /> You chose the {describeFamily(chosenFamily).name} design.
        </p>
      )}

      {data.phase === "choosing_design" && (
        <Link href={designsPagePath(referenceNo)} className={`mt-6 ${primaryButton}`}>Choose your design</Link>
      )}

      {data.phase === "live" && data.liveUrl && (
        <div className="mt-6 flex flex-col items-start gap-3">
          <a href={data.liveUrl} target="_blank" rel="noopener noreferrer" className={primaryButton}>
            Visit your website <ExternalLink size={18} aria-hidden="true" />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
          <p className="max-w-full font-mono text-sm text-gray-400 [overflow-wrap:anywhere]">{data.liveUrl.replace(/^https?:\/\//, "").replace(/\/$/, "")}</p>
        </div>
      )}

      {data.phase !== "live" && (
        <>
          <SegmentBar steps={data.steps} />
          <IntakeCard>
            {data.phase === "failed" && (
              <p className="mb-5 flex gap-2 text-sm text-[#ffb3ab]"><AlertTriangle size={18} className="shrink-0" aria-hidden="true" /> The step marked below didn&apos;t finish.</p>
            )}
            <Steps steps={data.steps} />
          </IntakeCard>
        </>
      )}

      {reconnecting && data.phase !== "live" && data.phase !== "failed" && (
        <p className="mt-4 text-xs text-gray-500" role="status">Having trouble reaching BUILD. Retrying…</p>
      )}
      {footer}
    </IntakeShell>
  );
}
