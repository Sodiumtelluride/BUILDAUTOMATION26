"use client"

import { useState, type KeyboardEvent, type PointerEvent } from "react"

// Chart size in SVG units; the SVG stretches to the card's width
const WIDTH = 600
const HEIGHT = 180
const TOP_PAD = 8 // room so a point at the top isn't cut off
const COLOR = "#3987e5" // series blue, checked for contrast on the dark background

export type ChartPoint = {
  label: string // short name under the axis, e.g. "Mon"
  title: string // full name in the tooltip, e.g. "Mon, Nov 3"
  value: number
}

/** Rounds the y-axis top up to a clean number so all three ticks are whole numbers. */
function axisTop(max: number) {
  return max <= 4 ? 4 : Math.ceil(max / 10) * 10
}

/**
 * Area chart for one series (e.g. projects started per day).
 * Hovering, or focusing it and using the arrow keys, shows a crosshair with the exact value.
 * A hidden table lists every value for screen readers.
 */
export default function AreaChart({ points, unit }: { points: ChartPoint[]; unit: string }) {
  // index of the day being inspected (null = none)
  const [active, setActive] = useState<number | null>(null)

  const last = points.length - 1
  const top = axisTop(Math.max(...points.map((p) => p.value)))
  const ticks = [0, top / 2, top]
  const x = (i: number) => (i / last) * WIDTH
  const y = (value: number) => HEIGHT - (value / top) * (HEIGHT - TOP_PAD)

  const line = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p.value)}`).join(" ")
  const area = `${line} L${WIDTH},${HEIGHT} L0,${HEIGHT} Z`
  const dot = active ?? last // the marked point: the hovered day, or today

  // Snap the pointer to the nearest day
  function onPointerMove(e: PointerEvent<HTMLDivElement>) {
    const box = e.currentTarget.getBoundingClientRect()
    const fraction = (e.clientX - box.left) / box.width
    setActive(Math.min(last, Math.max(0, Math.round(fraction * last))))
  }

  // Arrow keys move between days when the chart has keyboard focus
  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "ArrowLeft") setActive((a) => Math.max(0, (a ?? last) - 1))
    if (e.key === "ArrowRight") setActive((a) => Math.min(last, (a ?? last) + 1))
  }

  return (
    <figure>
      <div
        tabIndex={0}
        aria-label={`${unit} per day. Use the left and right arrow keys to read each day.`}
        onPointerMove={onPointerMove}
        onPointerLeave={() => setActive(null)}
        onFocus={() => setActive(last)}
        onBlur={() => setActive(null)}
        onKeyDown={onKeyDown}
        className="relative cursor-crosshair rounded-md outline-none focus-visible:ring-2 focus-visible:ring-blue-500/60"
      >
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} aria-hidden="true" className="block h-auto w-full overflow-visible">
          <defs>
            <linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor={COLOR} stopOpacity={0.2} />
              <stop offset="1" stopColor={COLOR} stopOpacity={0} />
            </linearGradient>
          </defs>
          {ticks.map((t) => (
            <line key={t} x1={0} x2={WIDTH} y1={y(t)} y2={y(t)} stroke="#2c2c2a" strokeWidth={1} vectorEffect="non-scaling-stroke" />
          ))}
          <path d={area} fill="url(#area-fill)" />
          <path d={line} fill="none" stroke={COLOR} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
          {active !== null && (
            <line x1={x(active)} x2={x(active)} y1={0} y2={HEIGHT} stroke="#898781" strokeWidth={1} vectorEffect="non-scaling-stroke" />
          )}
          <circle cx={x(dot)} cy={y(points[dot].value)} r={4} fill={COLOR} stroke="#09090b" strokeWidth={2} vectorEffect="non-scaling-stroke" />
        </svg>

        {/* y-axis numbers, sitting just above their gridlines */}
        {ticks.map((t) => (
          <span
            key={t}
            className="pointer-events-none absolute left-0 -translate-y-full pb-0.5 text-[11px] tabular-nums text-zinc-500"
            style={{ top: `${(y(t) / HEIGHT) * 100}%` }}
          >
            {t}
          </span>
        ))}

        {/* tooltip for the inspected day; kept inside the chart at both ends */}
        {active !== null && (
          <div
            className={`pointer-events-none absolute top-0 rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-xs shadow-lg ${
              active === 0 ? "" : active === last ? "-translate-x-full" : "-translate-x-1/2"
            }`}
            style={{ left: `${(x(active) / WIDTH) * 100}%` }}
          >
            <p className="text-sm font-semibold text-zinc-100">{points[active].value}</p>
            <p className="mt-0.5 flex items-center gap-1.5 whitespace-nowrap text-zinc-400">
              <span className="inline-block h-0.5 w-3 rounded-full" style={{ backgroundColor: COLOR }} />
              {unit} · {points[active].title}
            </p>
          </div>
        )}
      </div>

      <div className="mt-3 flex justify-between text-xs text-zinc-500">
        {points.map((p) => (
          <span key={p.title}>{p.label}</span>
        ))}
      </div>

      {/* the same numbers as a table, for screen readers */}
      <table className="sr-only">
        <caption>{unit} per day</caption>
        <thead>
          <tr>
            <th scope="col">Day</th>
            <th scope="col">{unit}</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.title}>
              <td>{p.title}</td>
              <td>{p.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}
