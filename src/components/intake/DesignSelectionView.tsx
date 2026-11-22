"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, Check, Eye, LoaderCircle, RefreshCw, Sparkles } from "lucide-react";
import {
  describeFamily,
  designPollDelayMs,
  orderOptions,
  type DesignOption,
  type DesignOptionsState,
} from "@/src/lib/intake/design-options";
import { PIPELINE_STEPS, SELECTION_INDEX, statusPagePath } from "@/src/lib/intake/job-status";
import { getDesignSource, type DesignSource } from "./design-source";
import { isIntakeMockEnabled } from "./mock-journey";
import { Eyebrow, IntakeHeading, IntakeShell, ReferenceFooter } from "./IntakeShell";
import { DesignPreviewDialog } from "./DesignPreviewDialog";

const MAX_RETRY_DELAY_MS = 60_000;
const HIDDEN_POLL_MS = 60_000;
const STEP_LABEL = `Step ${SELECTION_INDEX + 1} of ${PIPELINE_STEPS.length} · Your turn`;

type ViewState =
  | { kind: "loading" }
  | { kind: "ready"; data: DesignOptionsState }
  | { kind: "not_found" }
  | { kind: "unavailable" };

type SubmitState = { kind: "idle" } | { kind: "submitting" } | { kind: "error"; message: string };

// ---------- small pieces ----------

/** A live, non-interactive thumbnail: the site rendered 4x wide and scaled to a quarter so it shows a desktop layout. */
function Thumbnail({ option, eager = false }: { option: DesignOption; eager?: boolean }) {
  const [loaded, setLoaded] = useState(false);
  return (
    <div className="relative aspect-[4/3] overflow-hidden bg-white">
      {!loaded && <div className="absolute inset-0 bg-neutral-200 motion-safe:animate-pulse" />}
      <iframe
        src={option.previewUrl}
        title={`${describeFamily(option.family).name} design thumbnail`}
        loading={eager ? "eager" : "lazy"}
        tabIndex={-1}
        aria-hidden="true"
        sandbox="allow-scripts allow-same-origin"
        referrerPolicy="no-referrer"
        onLoad={() => setLoaded(true)}
        className="pointer-events-none absolute left-0 top-0 h-[400%] w-[400%] origin-top-left scale-25 border-0"
      />
    </div>
  );
}

function SkeletonCard() {
  return (
    <li className="overflow-hidden rounded-2xl border border-white/10 bg-[#1e1e1e]" aria-hidden="true">
      <div className="aspect-[4/3] bg-white/10 motion-safe:animate-pulse" />
      <div className="space-y-3 p-5">
        <div className="h-5 w-24 rounded bg-white/10 motion-safe:animate-pulse" />
        <div className="h-4 w-full rounded bg-white/5 motion-safe:animate-pulse" />
      </div>
    </li>
  );
}

// ---------- choosing ----------

function DesignCard({ option, checked, onCheck, onPreview }: { option: DesignOption; checked: boolean; onCheck: () => void; onPreview: () => void }) {
  const { name, description } = describeFamily(option.family);
  const inputId = `design-${option.id}`;
  return (
    <li className={`flex flex-col overflow-hidden rounded-2xl border bg-[#1e1e1e] text-left transition-shadow ${checked ? "border-[#DC4436] ring-2 ring-[#DC4436]" : "border-white/15 hover:border-white/30"}`}>
      <button type="button" onClick={onPreview} className="group relative block focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-white" aria-label={`Preview the ${name} design`}>
        <Thumbnail option={option} eager />
        <span className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition group-hover:bg-black/40 group-hover:opacity-100 group-focus-visible:bg-black/40 group-focus-visible:opacity-100">
          <span className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-black"><Eye size={16} aria-hidden="true" /> Preview</span>
        </span>
        {option.recommended && (
          <span className="absolute left-3 top-3 inline-flex items-center gap-1 rounded-full bg-black/80 px-3 py-1 text-xs font-semibold text-white">
            <Sparkles size={13} aria-hidden="true" /> Recommended for you
          </span>
        )}
      </button>
      <div className="flex flex-1 flex-col gap-4 p-5">
        <label htmlFor={inputId} className="flex flex-1 cursor-pointer items-start gap-3">
          <input
            id={inputId}
            type="radio"
            name="design"
            value={option.id}
            checked={checked}
            onChange={onCheck}
            className="mt-1 h-5 w-5 shrink-0 accent-[#DC4436]"
          />
          <span>
            <span className="block text-lg font-bold text-white">{name}</span>
            <span className="mt-1 block text-sm leading-relaxed text-gray-400">{description}</span>
          </span>
        </label>
        <button type="button" onClick={onPreview} className="inline-flex min-h-10 items-center justify-center gap-2 self-start rounded-full border border-white/20 px-4 text-sm font-semibold text-white hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-white">
          <Eye size={16} aria-hidden="true" /> Full preview
        </button>
      </div>
    </li>
  );
}

function ConfirmDialog({ option, submit, onConfirm, onCancel }: { option: DesignOption | null; submit: SubmitState; onConfirm: () => void; onCancel: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = dialog.current;
    if (!el) return;
    if (option && !el.open) el.showModal();
    if (!option && el.open) el.close();
  }, [option]);

  const name = option ? describeFamily(option.family).name : "";
  const busy = submit.kind === "submitting";
  return (
    <dialog
      ref={dialog}
      onCancel={(e) => { if (busy) e.preventDefault(); }}
      onClose={onCancel}
      aria-labelledby="confirm-design-title"
      className="m-auto w-[min(28rem,calc(100vw-2rem))] rounded-2xl border border-white/15 bg-neutral-950 p-6 text-left text-white backdrop:bg-black/70"
    >
      {option && (
        <>
          <h2 id="confirm-design-title" className="text-2xl font-bold">Build your site with {name}?</h2>
          <p className="mt-3 text-sm leading-relaxed text-gray-300">
            Next, we&apos;ll write your content into this design. You won&apos;t be able to switch designs after this.
          </p>
          {submit.kind === "error" && (
            <p role="alert" className="mt-4 flex gap-2 rounded-xl border border-[#DC4436]/60 bg-[#DC4436]/10 p-3 text-sm text-[#ffb3ab]">
              <AlertTriangle size={18} className="mt-0.5 shrink-0" aria-hidden="true" /> {submit.message}
            </p>
          )}
          <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <button type="button" onClick={onCancel} disabled={busy} className="min-h-11 rounded-full px-5 text-sm font-semibold text-white hover:bg-white/10 disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-white">
              Keep looking
            </button>
            <button type="button" onClick={onConfirm} disabled={busy} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-full bg-[#DC4436] px-5 text-sm font-semibold text-white hover:bg-[#c43a2d] disabled:opacity-70 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white">
              {busy && <LoaderCircle size={16} className="motion-safe:animate-spin" aria-hidden="true" />}
              {busy ? "Saving your choice…" : submit.kind === "error" ? "Try again" : `Yes, use ${name}`}
            </button>
          </div>
        </>
      )}
    </dialog>
  );
}

function Chooser({ data, referenceNo, source, onChosen, onState }: { data: DesignOptionsState; referenceNo: string; source: DesignSource; onChosen: (family: string) => void; onState: (s: DesignOptionsState) => void }) {
  const options = orderOptions(data.options);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [submit, setSubmit] = useState<SubmitState>({ kind: "idle" });
  const selected = options.find((o) => o.id === selectedId) ?? null;

  const confirm = async () => {
    if (!selected) return;
    setSubmit({ kind: "submitting" });
    const result = await source.select(referenceNo, selected.id);
    if (result.kind === "ok") {
      // Back to the status page, which now shows this step done.
      onChosen(selected.family);
    } else if (result.kind === "conflict") {
      setConfirming(false);
      setSubmit({ kind: "idle" });
      onState(result.data);
    } else if (result.kind === "rejected") {
      setSubmit({ kind: "error", message: "That design isn't available anymore. Close this and refresh the page to see your current options." });
    } else {
      setSubmit({ kind: "error", message: "We couldn't save your choice. Your selection is still here, so please try again in a moment." });
    }
  };

  const count = options.length;
  return (
    <>
      <Eyebrow>{STEP_LABEL}</Eyebrow>
      <IntakeHeading>Choose your design.</IntakeHeading>
      <p className="max-w-2xl text-sm leading-relaxed text-gray-300">
        {count === 1 ? "Here's the design we made for you." : `We made ${count} designs for your site. Each one has the same pages in a different visual style.`}{" "}
        Placeholder text stands in for now; we&apos;ll write your real content after you choose.
      </p>

      <fieldset className="mt-8 w-full">
        <legend className="sr-only">Design options</legend>
        <ul className={`grid gap-6 ${count === 1 ? "mx-auto max-w-md" : count === 2 ? "sm:grid-cols-2" : "sm:grid-cols-2 lg:grid-cols-3"}`}>
          {options.map((option, i) => (
            <DesignCard
              key={option.id}
              option={option}
              checked={selectedId === option.id}
              onCheck={() => setSelectedId(option.id)}
              onPreview={() => setPreviewIndex(i)}
            />
          ))}
        </ul>
      </fieldset>

      <div className="fixed inset-x-0 bottom-0 z-10 border-t border-white/10 bg-black/90 px-6 py-4 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-gray-300" aria-live="polite">
            {selected ? <>Selected: <span className="font-semibold text-white">{describeFamily(selected.family).name}</span></> : "Select a design to continue."}
          </p>
          <button
            type="button"
            disabled={!selected}
            onClick={() => { setSubmit({ kind: "idle" }); setConfirming(true); }}
            className="min-h-12 w-full rounded-full bg-[#DC4436] px-6 text-base font-semibold text-white hover:bg-[#c43a2d] disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-gray-500 sm:w-auto focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          >
            {selected ? `Continue with ${describeFamily(selected.family).name}` : "Continue"}
          </button>
        </div>
      </div>

      <DesignPreviewDialog
        options={options}
        index={previewIndex}
        onIndexChange={setPreviewIndex}
        onClose={() => setPreviewIndex(null)}
        onChoose={(id) => { setSelectedId(id); setPreviewIndex(null); }}
        chosenId={selectedId}
      />
      <ConfirmDialog
        option={confirming ? selected : null}
        submit={submit}
        onConfirm={confirm}
        onCancel={() => { if (submit.kind !== "submitting") setConfirming(false); }}
      />
    </>
  );
}

// ---------- page ----------

export function DesignSelectionView({ referenceNo, source: injected }: { referenceNo: string; source?: DesignSource }) {
  const [source] = useState<DesignSource>(() => injected ?? getDesignSource());
  const [view, setView] = useState<ViewState>({ kind: "loading" });
  const [reconnecting, setReconnecting] = useState(false);
  const [runId, setRunId] = useState(0);
  const router = useRouter();
  const badge = isIntakeMockEnabled() ? "Demo data" : undefined;
  const status = view.kind === "ready" ? view.data.status : null;

  // Tell someone in another tab that it's their turn.
  useEffect(() => {
    if (status === "ready") document.title = "Your designs are ready · BUILD";
    else if (status === "generating") document.title = "Creating your designs… · BUILD";
  }, [status]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    let controller: AbortController | null = null;
    let failures = 0;
    let stopped = false;
    let disposed = false;

    const load = async () => {
      if (timer) clearTimeout(timer);
      controller?.abort();
      const abort = new AbortController();
      controller = abort;
      let nextDelay: number | null;
      try {
        const result = await source.load(referenceNo, abort.signal);
        if (disposed) return;
        if (result.kind === "ok") {
          failures = 0;
          setReconnecting(false);
          setView({ kind: "ready", data: result.data });
          nextDelay = designPollDelayMs(result.data.status);
        } else if (result.kind === "not_found") {
          setView({ kind: "not_found" });
          nextDelay = null;
        } else {
          failures += 1;
          setReconnecting(true);
          setView((prev) => (prev.kind === "loading" ? { kind: "unavailable" } : prev));
          nextDelay = Math.min(5_000 * 2 ** failures, MAX_RETRY_DELAY_MS);
        }
      } catch {
        return; // aborted
      }
      if (nextDelay === null) stopped = true;
      else timer = setTimeout(load, document.hidden ? Math.max(nextDelay, HIDDEN_POLL_MS) : nextDelay);
    };

    const onVisibility = () => {
      if (!document.hidden && !stopped) load();
    };

    load();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      disposed = true;
      document.removeEventListener("visibilitychange", onVisibility);
      if (timer) clearTimeout(timer);
      controller?.abort();
    };
  }, [referenceNo, source, runId]);

  const retry = () => {
    setView((prev) => (prev.kind === "unavailable" ? { kind: "loading" } : prev));
    setRunId((n) => n + 1);
  };

  const footer = <ReferenceFooter referenceNo={referenceNo} />;
  const statusLink = (label: string) => (
    <Link href={statusPagePath(referenceNo)} className="mt-6 inline-flex min-h-11 items-center rounded-full bg-white px-5 text-sm font-semibold text-black hover:bg-gray-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white">{label}</Link>
  );

  if (view.kind === "loading") {
    return (
      <IntakeShell subtitle="Choose your design" badge={badge}>
        <p className="flex items-center gap-3 text-gray-300" role="status">
          <LoaderCircle size={20} className="motion-safe:animate-spin" aria-hidden="true" /> Loading your designs…
        </p>
        {footer}
      </IntakeShell>
    );
  }

  if (view.kind === "not_found") {
    return (
      <IntakeShell subtitle="Choose your design" badge={badge}>
        <IntakeHeading>We couldn&apos;t find designs for this project.</IntakeHeading>
        <p className="text-sm leading-relaxed text-gray-300">Check that the link matches the one we sent you, or see where your project is now.</p>
        {statusLink("Check your project's progress")}
        {footer}
      </IntakeShell>
    );
  }

  if (view.kind === "unavailable") {
    return (
      <IntakeShell subtitle="Choose your design" badge={badge}>
        <IntakeHeading>We can&apos;t load your designs right now.</IntakeHeading>
        <p className="text-sm leading-relaxed text-gray-300">Your project is safe. We&apos;ll keep trying in the background.</p>
        <button type="button" onClick={retry} className="mt-6 inline-flex min-h-11 items-center gap-2 rounded-full bg-white px-5 text-sm font-semibold text-black hover:bg-gray-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white">
          <RefreshCw size={16} aria-hidden="true" /> Try again
        </button>
        {footer}
      </IntakeShell>
    );
  }

  const { data } = view;

  if (data.status === "generating") {
    return (
      <IntakeShell subtitle="Choose your design" badge={badge} wide>
        <Eyebrow>{STEP_LABEL}</Eyebrow>
        <IntakeHeading>We&apos;re still building your designs.</IntakeHeading>
        <p className="max-w-2xl text-sm leading-relaxed text-gray-300" role="status">
          They&apos;ll appear here in a few minutes, and this page updates by itself.
        </p>
        <ul className="mt-8 grid w-full gap-6 sm:grid-cols-2 lg:grid-cols-3">
          <SkeletonCard /><SkeletonCard /><SkeletonCard />
        </ul>
        {reconnecting && <p className="mt-4 text-xs text-gray-500" role="status">Having trouble reaching BUILD. Retrying…</p>}
        {footer}
      </IntakeShell>
    );
  }

  if (data.status === "failed") {
    return (
      <IntakeShell subtitle="Choose your design" badge={badge}>
        <IntakeHeading>We couldn&apos;t create your designs.</IntakeHeading>
        <p className="flex gap-2 text-sm leading-relaxed text-gray-300">
          <AlertTriangle size={18} className="mt-0.5 shrink-0 text-[#ffb3ab]" aria-hidden="true" />
          The BUILD team has been notified and will follow up by email. Please don&apos;t submit the form again. If you have questions, reply to your confirmation email and include your reference number.
        </p>
        {footer}
      </IntakeShell>
    );
  }

  if (data.status === "submitted") {
    // Reached by revisiting the link after choosing.
    const chosen = data.options.find((o) => o.id === data.selectedOptionId) ?? null;
    const name = chosen ? describeFamily(chosen.family).name : null;
    return (
      <IntakeShell subtitle="Choose your design" badge={badge}>
        <IntakeHeading>{name ? `You chose ${name}.` : "Your design is chosen."}</IntakeHeading>
        <p className="flex gap-2 text-sm leading-relaxed text-gray-300">
          <Check size={18} className="mt-0.5 shrink-0 text-[#FF7A6E]" aria-hidden="true" />
          We&apos;re writing your content into this design. A BUILD team member reviews every site before it goes live.
        </p>
        {chosen && (
          <div className="mt-6 w-full max-w-sm overflow-hidden rounded-2xl border border-white/15">
            <Thumbnail option={chosen} eager />
          </div>
        )}
        {statusLink("Track your progress")}
        {footer}
      </IntakeShell>
    );
  }

  return (
    <IntakeShell subtitle="Choose your design" badge={badge} wide bottomBar>
      <Chooser
        data={data}
        referenceNo={referenceNo}
        source={source}
        onState={(next) => setView({ kind: "ready", data: next })}
        onChosen={(family) => router.replace(`${statusPagePath(referenceNo)}?chose=${encodeURIComponent(family)}`)}
      />
      {footer}
    </IntakeShell>
  );
}
