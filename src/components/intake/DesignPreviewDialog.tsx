"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, ExternalLink, LoaderCircle, Monitor, Smartphone, X } from "lucide-react";
import { describeFamily, type DesignOption } from "@/src/lib/intake/design-options";

type Device = "desktop" | "mobile";

interface Props {
  options: DesignOption[];
  /** Index into options of the design being previewed; null = closed. */
  index: number | null;
  onIndexChange: (index: number) => void;
  onClose: () => void;
  onChoose: (optionId: string) => void;
  chosenId: string | null;
}

// Full-size preview. A native <dialog> gives focus trapping, Esc to close and
// an inert page behind it for free.
export function DesignPreviewDialog({ options, index, onIndexChange, onClose, onChoose, chosenId }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [device, setDevice] = useState<Device>("desktop");
  const [loadedUrl, setLoadedUrl] = useState<string | null>(null);
  const open = index !== null;
  const option = open ? options[index] : null;

  useEffect(() => {
    const el = dialog.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  const step = (delta: number) => {
    if (index !== null) onIndexChange((index + delta + options.length) % options.length);
  };

  return (
    <dialog
      ref={dialog}
      onClose={onClose}
      onKeyDown={(e) => {
        if (options.length < 2) return;
        if (e.key === "ArrowRight") step(1);
        if (e.key === "ArrowLeft") step(-1);
      }}
      aria-labelledby="design-preview-title"
      className="m-0 h-dvh max-h-none w-screen max-w-none bg-neutral-950 p-0 text-left text-white backdrop:bg-black/80"
    >
      {option && index !== null && <PreviewBody {...{ option, index, total: options.length, device, setDevice, loadedUrl, setLoadedUrl, step, onClose, onChoose, isChosen: chosenId === option.id }} />}
    </dialog>
  );
}

interface BodyProps {
  option: DesignOption;
  index: number;
  total: number;
  device: Device;
  setDevice: (d: Device) => void;
  loadedUrl: string | null;
  setLoadedUrl: (url: string) => void;
  step: (delta: number) => void;
  onClose: () => void;
  onChoose: (optionId: string) => void;
  isChosen: boolean;
}

function PreviewBody({ option, index, total, device, setDevice, loadedUrl, setLoadedUrl, step, onClose, onChoose, isChosen }: BodyProps) {
  const { name, description } = describeFamily(option.family);
  const canOpenTab = !option.previewUrl.startsWith("data:");
  return (
      <div className="flex h-full flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-white/10 px-4 py-3">
          <div className="mr-auto min-w-0">
            <h2 id="design-preview-title" className="text-lg font-bold">
              {name} <span className="font-normal text-gray-400">· {index + 1} of {total}</span>
            </h2>
            <p className="truncate text-sm text-gray-400">{description}</p>
          </div>

          <div role="group" aria-label="Preview size" className="flex rounded-full border border-white/20 p-1">
            {(["desktop", "mobile"] as const).map((d) => (
              <button
                key={d}
                type="button"
                aria-pressed={device === d}
                onClick={() => setDevice(d)}
                className={`inline-flex min-h-9 items-center gap-1.5 rounded-full px-3 text-sm capitalize focus-visible:outline-2 focus-visible:outline-white ${device === d ? "bg-white text-black" : "text-gray-300 hover:bg-white/10"}`}
              >
                {d === "desktop" ? <Monitor size={15} aria-hidden="true" /> : <Smartphone size={15} aria-hidden="true" />} {d}
              </button>
            ))}
          </div>

          {canOpenTab && (
            <a href={option.previewUrl} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-10 items-center gap-1.5 rounded-full px-3 text-sm text-gray-300 hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-white">
              Open <ExternalLink size={15} aria-hidden="true" /><span className="sr-only">(opens in a new tab)</span>
            </a>
          )}
          <button type="button" onClick={onClose} aria-label="Close preview" className="inline-flex h-10 w-10 items-center justify-center rounded-full hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-white">
            <X size={20} aria-hidden="true" />
          </button>
        </header>

        <div className="relative flex flex-1 justify-center overflow-hidden bg-neutral-900 p-3 sm:p-6">
          <div className={`relative h-full overflow-hidden rounded-lg bg-white shadow-2xl transition-[width] duration-300 ${device === "mobile" ? "w-[390px] max-w-full" : "w-full"}`}>
            {loadedUrl !== option.previewUrl && (
              <div className="absolute inset-0 flex items-center justify-center bg-neutral-100" role="status">
                <LoaderCircle size={28} className="text-neutral-400 motion-safe:animate-spin" aria-hidden="true" />
                <span className="sr-only">Loading preview</span>
              </div>
            )}
            <iframe
              key={option.id}
              src={option.previewUrl}
              title={`${name} design, full preview`}
              sandbox="allow-scripts allow-same-origin"
              referrerPolicy="no-referrer"
              onLoad={() => setLoadedUrl(option.previewUrl)}
              className="h-full w-full border-0"
            />
          </div>
        </div>

        <footer className="flex items-center gap-3 border-t border-white/10 px-4 py-3">
          {total > 1 && (
            <div className="flex gap-1">
              <button type="button" onClick={() => step(-1)} aria-label="Previous design" className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/20 hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-white">
                <ChevronLeft size={20} aria-hidden="true" />
              </button>
              <button type="button" onClick={() => step(1)} aria-label="Next design" className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/20 hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-white">
                <ChevronRight size={20} aria-hidden="true" />
              </button>
            </div>
          )}
          <p className="mr-auto hidden text-sm text-gray-400 sm:block">Placeholder text stands in for your content.</p>
          <button
            type="button"
            onClick={() => onChoose(option.id)}
            aria-pressed={isChosen}
            className={`min-h-11 rounded-full px-5 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white ${isChosen ? "bg-white text-black" : "bg-[#DC4436] text-white hover:bg-[#c43a2d]"}`}
          >
            {isChosen ? `${name} selected` : `Select ${name}`}
          </button>
        </footer>
      </div>
  );
}
