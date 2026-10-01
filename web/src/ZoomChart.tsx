import { cloneElement, memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent, PointerEvent as ReactPointerEvent, ReactElement } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceLine, Tooltip, XAxis, YAxis } from 'recharts'
import type { DotProps, TooltipProps } from 'recharts'
import type { EventKind } from './api'

export type ChartRow = Record<string, number | string | null | undefined>

export interface ChartSeries {
  key: string
  name: string
  color: string
}

export interface ChartEvent {
  x: number
  series: string
  kind: EventKind
  label: string
  priority: number
}

export interface Tick {
  value: number
  label: string
}

interface View {
  x0: number
  x1: number
  y0: number
  y1: number
}

interface Props {
  data: ChartRow[]
  xKey: string
  series: ChartSeries[]
  ticks: (x0: number, x1: number, maxTicks: number) => Tick[]
  tooltip: ReactElement
  yLabel: string
  xLabel?: string
  events?: ChartEvent[]
  hovered?: string | null
  connectNulls?: boolean
  angledTicks?: boolean
  lineWidth?: number
  lineType?: 'linear' | 'step' | 'stepBefore' | 'stepAfter'
  aspectRatio?: number
  minHeight?: number
  maxHeight?: number
  /** Fixed y extent, instead of measuring the data. */
  yBounds?: [number, number]
  yTickFormatter?: (value: number) => string
  yTickStep?: number
}

const DEFAULT_ASPECT = 2.2
const DEFAULT_MIN_HEIGHT = 340
const DEFAULT_MAX_HEIGHT = 780
const MARGIN = { top: 20, right: 24, bottom: 8, left: 8 }
const Y_AXIS_WIDTH = 64
const MIN_X_SPAN = 3
const LABEL_LIMIT = 14
const MAX_MARKERS = 400
const LABEL_OFFSETS = [-20, 20, -42, 42, -64, 64, -86, 86]

let measureContext: CanvasRenderingContext2D | null | undefined

function measureText(text: string): number {
  if (measureContext === undefined) {
    measureContext = document.createElement('canvas').getContext('2d')
    if (measureContext) measureContext.font = `11px ${getComputedStyle(document.body).fontFamily}`
  }
  return measureContext ? measureContext.measureText(text).width : text.length * 6.6
}

const EVENT_LEGEND: Record<EventKind, string> = {
  title: 'Championship',
  runnerup: 'Title-game loss',
  conference: 'Conference / league title',
  arrival: 'Arrival / new team',
  departure: 'Final season',
  move: 'Relocation',
  season: 'Landmark season',
  milestone: 'Milestone',
}

function niceStep(span: number, count: number, minStep: number): number {
  const raw = span / Math.max(1, count)
  const magnitude = 10 ** Math.floor(Math.log10(raw || 1))
  const normalized = raw / magnitude
  const nice = normalized < 1.5 ? 1 : normalized < 3 ? 2 : normalized < 7 ? 5 : 10
  return Math.max(minStep, nice * magnitude)
}

/** Evenly spaced round-number ticks across [x0, x1]. */
export function numericTicks(
  x0: number,
  x1: number,
  maxTicks: number,
  format: (value: number) => string = String,
): Tick[] {
  const step = niceStep(x1 - x0, maxTicks, 1)
  const ticks: Tick[] = []
  for (let value = Math.ceil(x0 / step) * step; value <= x1; value += step) {
    ticks.push({ value, label: format(value) })
  }
  return ticks
}

/** Season ticks for week-by-week walks; week ticks appear once only a few seasons are in view. */
export function stepTicks(rows: ChartRow[], x0: number, x1: number, maxTicks: number): Tick[] {
  const first = Math.max(0, Math.ceil(x0))
  const last = Math.min(rows.length - 1, Math.floor(x1))
  const seasonStarts: Tick[] = []
  for (let index = first; index <= last; index += 1) {
    const season = rows[index].season as number
    if (season && (index === 0 || rows[index - 1].season !== season)) {
      seasonStarts.push({ value: index, label: String(season) })
    }
  }

  const visible = last - first + 1
  if (visible <= maxTicks * 1.2 || seasonStarts.length <= 2) {
    const stride = Math.max(1, Math.ceil(visible / maxTicks))
    const ticks: Tick[] = []
    for (let index = first; index <= last; index += stride) {
      ticks.push({ value: index, label: String(rows[index].label ?? '') })
    }
    return ticks
  }
  if (seasonStarts.length <= maxTicks) return seasonStarts
  const step = [2, 5, 10, 20, 25, 50].find((value) => seasonStarts.length / value <= maxTicks) ?? 50
  return seasonStarts.filter((tick) => Number(tick.label) % step === 0)
}

function clampView(view: View, full: View): View | null {
  const fullWidth = full.x1 - full.x0
  const fullHeight = full.y1 - full.y0
  const width = view.x1 - view.x0
  if (width >= fullWidth * 0.999) return null
  const height = Math.min(view.y1 - view.y0, fullHeight)
  const x0 = Math.min(Math.max(view.x0, full.x0), full.x1 - width)
  const y0 = Math.min(Math.max(view.y0, full.y0), full.y1 - height)
  return { x0, x1: x0 + width, y0, y1: y0 + height }
}

function lowerBound(values: number[], target: number): number {
  let lo = 0
  let hi = values.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (values[mid] < target) lo = mid + 1
    else hi = mid
  }
  return lo
}

function starPath(cx: number, cy: number, outer: number, inner: number): string {
  const points = Array.from({ length: 10 }, (_, index) => {
    const radius = index % 2 === 0 ? outer : inner
    const angle = -Math.PI / 2 + (index * Math.PI) / 5
    return `${(cx + radius * Math.cos(angle)).toFixed(1)},${(cy + radius * Math.sin(angle)).toFixed(1)}`
  })
  return `M${points.join('L')}Z`
}

function Marker({ kind, x, y, color }: { kind: EventKind; x: number; y: number; color: string }) {
  switch (kind) {
    case 'title':
      return <path d={starPath(x, y, 7.5, 3.2)} fill="#f5c542" stroke="#1a1d29" strokeWidth={1} />
    case 'runnerup':
      return <circle cx={x} cy={y} r={4.5} fill="#c3cad9" stroke="#1a1d29" />
    case 'conference':
      return <circle cx={x} cy={y} r={4.5} fill="#7aa2f7" stroke="#1a1d29" />
    case 'arrival':
      return <path d={`M${x},${y - 6}L${x + 5.5},${y + 4}L${x - 5.5},${y + 4}Z`} fill={color} stroke="#ffffff" strokeWidth={1.2} />
    case 'departure':
      return <path d={`M${x},${y + 6}L${x + 5.5},${y - 4}L${x - 5.5},${y - 4}Z`} fill="#0d1019" stroke={color} strokeWidth={1.6} />
    case 'move':
      return <rect x={x - 4.5} y={y - 4.5} width={9} height={9} fill="#bb9af7" stroke="#1a1d29" />
    case 'season':
      return <path d={`M${x},${y - 6}L${x + 6},${y}L${x},${y + 6}L${x - 6},${y}Z`} fill="#9ece6a" stroke="#1a1d29" />
    default:
      return <circle cx={x} cy={y} r={4.5} fill="none" stroke="#e0af68" strokeWidth={2} />
  }
}

interface MiniMapProps {
  data: ChartRow[]
  xKey: string
  series: ChartSeries[]
  full: View
  width: number
  height: number
  lineType?: 'linear' | 'step' | 'stepBefore' | 'stepAfter'
}

const MiniMapLines = memo(function MiniMapLines({
  data,
  xKey,
  series,
  full,
  width,
  height,
  lineType = 'linear',
}: MiniMapProps) {
  const stride = Math.max(1, Math.ceil(data.length / width))
  const sx = (x: number) => ((x - full.x0) / (full.x1 - full.x0)) * width
  const sy = (y: number) => ((full.y1 - y) / (full.y1 - full.y0)) * height
  return (
    <>
      {series.map((entry) => {
        let path = ''
        let pen = false
        for (let index = 0; index < data.length; index += stride) {
          const value = data[index][entry.key]
          if (typeof value !== 'number') {
            pen = false
            continue
          }
          const curX = sx(Number(data[index][xKey]))
          const curY = sy(value)
          if (!pen) {
            path += `M${curX.toFixed(1)},${curY.toFixed(1)}`
            pen = true
          } else if (lineType === 'stepAfter') {
            path += `H${curX.toFixed(1)}V${curY.toFixed(1)}`
          } else {
            path += `L${curX.toFixed(1)},${curY.toFixed(1)}`
          }
        }
        return <path key={entry.key} d={path} fill="none" stroke={entry.color} strokeWidth={1} strokeOpacity={0.8} />
      })}
    </>
  )
})

export default function ZoomChart({
  data,
  xKey,
  series,
  ticks,
  tooltip,
  yLabel,
  xLabel,
  events = [],
  hovered = null,
  connectNulls = false,
  angledTicks = false,
  lineWidth = 1.8,
  lineType = 'linear',
  aspectRatio = DEFAULT_ASPECT,
  minHeight = DEFAULT_MIN_HEIGHT,
  maxHeight = DEFAULT_MAX_HEIGHT,
  yBounds,
  yTickFormatter,
  yTickStep,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  const [view, setView] = useState<View | null>(null)
  const [dragging, setDragging] = useState(false)
  const [hoveredEvent, setHoveredEvent] = useState<number | null>(null)
  const viewRef = useRef<View | null>(null)
  const frame = useRef(0)
  const drag = useRef<{ x: number; y: number; start: View } | null>(null)

  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  const height = Math.round(Math.min(maxHeight, Math.max(minHeight, width / aspectRatio)))
  const xAxisHeight = angledTicks ? 64 : xLabel ? 44 : 30
  const plot = {
    left: MARGIN.left + Y_AXIS_WIDTH,
    top: MARGIN.top,
    width: Math.max(1, width - MARGIN.left - Y_AXIS_WIDTH - MARGIN.right),
    height: Math.max(1, height - MARGIN.top - MARGIN.bottom - xAxisHeight),
  }

  const xs = useMemo(() => data.map((row) => Number(row[xKey])), [data, xKey])
  const full = useMemo<View | null>(() => {
    if (!data.length) return null
    let lo = 0
    let hi = 0
    for (const row of data) {
      for (const entry of series) {
        const value = row[entry.key]
        if (typeof value === 'number') {
          if (value < lo) lo = value
          if (value > hi) hi = value
        }
      }
    }
    const pad = Math.max(1, (hi - lo) * 0.05)
    const x0 = xs[0]
    const x1 = xs[xs.length - 1]
    return {
      x0,
      x1: x1 > x0 ? x1 : x0 + 1,
      y0: yBounds ? yBounds[0] : lo - pad,
      y1: yBounds ? yBounds[1] : hi + pad,
    }
  }, [data, series, xs, yBounds])

  useEffect(() => {
    viewRef.current = null
    setView(null)
  }, [data])

  const current = full ? (view ? clampView(view, full) ?? full : full) : null
  const zoomed = current !== null && current !== full

  // Handlers run outside React's render cycle, so they read the latest layout from refs.
  const layout = useRef({ full, plot })
  layout.current = { full, plot }

  const commit = useCallback((next: View | null) => {
    viewRef.current = next
    if (!frame.current) {
      frame.current = requestAnimationFrame(() => {
        frame.current = 0
        setView(viewRef.current)
      })
    }
  }, [])

  const zoomAt = useCallback(
    (factor: number, px: number, py: number) => {
      const { full: extent, plot: area } = layout.current
      if (!extent) return
      const base = viewRef.current ? clampView(viewRef.current, extent) ?? extent : extent
      const w = base.x1 - base.x0
      const h = base.y1 - base.y0
      const fullWidth = extent.x1 - extent.x0
      const nextWidth = Math.min(fullWidth, Math.max(Math.min(MIN_X_SPAN, fullWidth), w / factor))
      const ratio = nextWidth / w
      const fx = Math.min(1, Math.max(0, (px - area.left) / area.width))
      const fy = Math.min(1, Math.max(0, (py - area.top) / area.height))
      const anchorX = base.x0 + fx * w
      const anchorY = base.y1 - fy * h
      const y1 = anchorY + fy * h * ratio
      commit(
        clampView(
          { x0: anchorX - fx * nextWidth, x1: anchorX - fx * nextWidth + nextWidth, y0: y1 - h * ratio, y1 },
          extent,
        ),
      )
    },
    [commit],
  )

  const zoomAtCenter = (factor: number) =>
    zoomAt(factor, plot.left + plot.width / 2, plot.top + plot.height / 2)

  const panBy = (fx: number, fy: number) => {
    if (!full || !current || !zoomed) return
    const dx = (current.x1 - current.x0) * fx
    const dy = (current.y1 - current.y0) * fy
    commit(clampView({ x0: current.x0 + dx, x1: current.x1 + dx, y0: current.y0 + dy, y1: current.y1 + dy }, full))
  }

  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    const onWheel = (event: WheelEvent) => {
      const area = layout.current.plot
      const rect = element.getBoundingClientRect()
      const px = event.clientX - rect.left
      const py = event.clientY - rect.top
      if (px < area.left || px > area.left + area.width || py < area.top || py > area.top + area.height) return
      event.preventDefault()
      const delta = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaMode === 2 ? event.deltaY * 400 : event.deltaY
      // Pinch gestures arrive as ctrl+wheel with small deltas.
      zoomAt(Math.exp(-delta * (event.ctrlKey ? 0.01 : 0.002)), px, py)
    }
    element.addEventListener('wheel', onWheel, { passive: false })
    return () => element.removeEventListener('wheel', onWheel)
  }, [zoomAt])

  useEffect(() => () => cancelAnimationFrame(frame.current), [])

  const insidePlot = (event: ReactPointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    const px = event.clientX - rect.left
    const py = event.clientY - rect.top
    return px >= plot.left && px <= plot.left + plot.width && py >= plot.top && py <= plot.top + plot.height
  }

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || !zoomed || !current || !insidePlot(event)) return
    drag.current = { x: event.clientX, y: event.clientY, start: current }
    event.currentTarget.setPointerCapture(event.pointerId)
    setDragging(true)
  }

  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const state = drag.current
    if (!state || !full) return
    const w = state.start.x1 - state.start.x0
    const h = state.start.y1 - state.start.y0
    const dx = ((event.clientX - state.x) / plot.width) * w
    const dy = ((event.clientY - state.y) / plot.height) * h
    commit(
      clampView(
        { x0: state.start.x0 - dx, x1: state.start.x1 - dx, y0: state.start.y0 + dy, y1: state.start.y1 + dy },
        full,
      ),
    )
  }

  const endDrag = () => {
    drag.current = null
    setDragging(false)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const actions: Record<string, () => void> = {
      '+': () => zoomAtCenter(1.5),
      '=': () => zoomAtCenter(1.5),
      '-': () => zoomAtCenter(1 / 1.5),
      '0': () => commit(null),
      ArrowLeft: () => panBy(-0.1, 0),
      ArrowRight: () => panBy(0.1, 0),
      ArrowUp: () => panBy(0, 0.1),
      ArrowDown: () => panBy(0, -0.1),
    }
    const action = actions[event.key]
    if (action) {
      event.preventDefault()
      action()
    }
  }

  const visibleRows = useMemo(() => {
    if (!current) return data
    const start = Math.max(0, lowerBound(xs, current.x0) - 1)
    const end = Math.min(data.length, lowerBound(xs, current.x1) + 1)
    const slice = data.slice(start, end)
    const budget = Math.max(200, Math.round(plot.width * 1.5))
    if (slice.length <= budget) return slice
    const stride = Math.ceil(slice.length / budget)
    return slice.filter((_, index) => index % stride === 0 || index === slice.length - 1)
  }, [data, xs, current, plot.width])

  const maxXTicks = Math.max(2, Math.floor(plot.width / (angledTicks ? 34 : 64)))
  const xTicks = useMemo(
    () => (current ? ticks(current.x0, current.x1, maxXTicks) : []),
    [ticks, current, maxXTicks],
  )
  const xTickLabels = useMemo(() => new Map(xTicks.map((tick) => [tick.value, tick.label])), [xTicks])
  const yTicks = useMemo(() => {
    if (!current) return []
    const step =
      yTickStep ?? niceStep(current.y1 - current.y0, Math.max(3, Math.floor(plot.height / 48)), 1)
    const values: number[] = []
    for (let value = Math.ceil(current.y0 / step) * step; value <= current.y1; value += step) values.push(value)
    return values
  }, [current, plot.height, yTickStep])

  const rowByX = useMemo(() => new Map(data.map((row) => [Number(row[xKey]), row])), [data, xKey])
  const colorBySeries = useMemo(() => new Map(series.map((entry) => [entry.key, entry.color])), [series])
  const nameBySeries = useMemo(() => new Map(series.map((entry) => [entry.key, entry.name])), [series])
  const zoom = full && current ? (full.x1 - full.x0) / (current.x1 - current.x0) : 1
  const level = zoom >= 5 ? 3 : zoom >= 2 ? 2 : zoomed ? 1 : 0

  const { markers, hiddenCount } = useMemo(() => {
    if (!current) return { markers: [], hiddenCount: 0 }
    const w = current.x1 - current.x0
    const h = current.y1 - current.y0
    let hidden = 0
    const placed = []
    for (const [index, event] of events.entries()) {
      const color = colorBySeries.get(event.series)
      if (!color || event.x < current.x0 || event.x > current.x1) continue
      const value = rowByX.get(event.x)?.[event.series]
      if (typeof value !== 'number' || value < current.y0 || value > current.y1) continue
      if (event.priority > level) {
        hidden += 1
        continue
      }
      placed.push({
        ...event,
        label: series.length > 1 ? `${nameBySeries.get(event.series)} · ${event.label}` : event.label,
        id: index,
        color,
        px: plot.left + ((event.x - current.x0) / w) * plot.width,
        py: plot.top + ((current.y1 - value) / h) * plot.height,
      })
    }
    placed.sort((a, b) => a.priority - b.priority || a.px - b.px)
    return { markers: placed.slice(0, MAX_MARKERS), hiddenCount: hidden }
  }, [events, current, colorBySeries, nameBySeries, series.length, rowByX, level, plot.left, plot.top, plot.width, plot.height])

  const minimapSize = useMemo(() => {
    if (height < 320) {
      return { width: 140, height: 48 }
    }
    return { width: 184, height: 76 }
  }, [height])

  const labels = useMemo(() => {
    const focus = hovered ? markers.filter((marker) => marker.series === hovered) : []
    let candidates = focus.length && focus.length <= LABEL_LIMIT ? focus : []
    if (!candidates.length) {
      // Label whole priority tiers, most important first, while they still fit.
      for (const tier of [1, 2, 3]) {
        const next = markers.filter((marker) => marker.priority <= tier)
        if (next.length > LABEL_LIMIT) break
        candidates = next
      }
    }
    const obstacles: { x0: number; x1: number; y0: number; y1: number }[] = []
    if (zoomed) {
      const left = width - MARGIN.right - 8 - minimapSize.width
      obstacles.push({
        x0: left,
        x1: left + minimapSize.width,
        y0: plot.top + 8,
        y1: plot.top + 8 + minimapSize.height,
      })
    }
    const result = []
    for (const marker of [...candidates].sort((a, b) => a.priority - b.priority || a.px - b.px)) {
      const textWidth = measureText(marker.label) + 14
      const cx = Math.min(Math.max(marker.px, plot.left + textWidth / 2), plot.left + plot.width - textWidth / 2)
      for (const offset of LABEL_OFFSETS) {
        const y = marker.py + offset
        if (y - 9 < plot.top || y + 9 > plot.top + plot.height) continue
        const box = { x0: cx - textWidth / 2 - 3, x1: cx + textWidth / 2 + 3, y0: y - 11, y1: y + 11 }
        if (obstacles.some((other) => box.x0 < other.x1 && box.x1 > other.x0 && box.y0 < other.y1 && box.y1 > other.y0)) {
          continue
        }
        obstacles.push(box)
        result.push({ ...marker, cx, y, textWidth })
        break
      }
    }
    return result
  }, [markers, hovered, zoomed, width, minimapSize, plot.left, plot.top, plot.width, plot.height])

  const hoverLabel = hoveredEvent === null ? null : markers.find((marker) => marker.id === hoveredEvent)
  const renderActiveDot = (props: DotProps): ReactElement => {
    const { cx = -1, cy = -1, stroke } = props
    if (cy < plot.top || cy > plot.top + plot.height) return <g />
    return <circle cx={cx} cy={cy} r={4} fill={stroke} stroke="#ffffff" strokeWidth={1.5} />
  }
  const legendKinds = useMemo(
    () => (Object.keys(EVENT_LEGEND) as EventKind[]).filter((kind) => events.some((event) => event.kind === kind)),
    [events],
  )

  const minimap =
    zoomed && full && current
      ? {
          x: ((current.x0 - full.x0) / (full.x1 - full.x0)) * minimapSize.width,
          y: ((full.y1 - current.y1) / (full.y1 - full.y0)) * minimapSize.height,
          w: ((current.x1 - current.x0) / (full.x1 - full.x0)) * minimapSize.width,
          h: ((current.y1 - current.y0) / (full.y1 - full.y0)) * minimapSize.height,
        }
      : null

  const centerFromMinimap = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!full || !current || (event.type === 'pointermove' && event.buttons !== 1)) return
    event.stopPropagation()
    const rect = event.currentTarget.getBoundingClientRect()
    const cx = full.x0 + ((event.clientX - rect.left) / rect.width) * (full.x1 - full.x0)
    const cy = full.y1 - ((event.clientY - rect.top) / rect.height) * (full.y1 - full.y0)
    const w = current.x1 - current.x0
    const h = current.y1 - current.y0
    commit(clampView({ x0: cx - w / 2, x1: cx + w / 2, y0: cy - h / 2, y1: cy + h / 2 }, full))
  }

  return (
    <>
      <div className="zoom-toolbar">
        <div className="event-legend">
          {legendKinds.map((kind) => (
            <span key={kind} className="event-legend-item">
              <svg width={14} height={14} aria-hidden="true">
                <Marker kind={kind} x={7} y={7} color="#7b839c" />
              </svg>
              {EVENT_LEGEND[kind]}
            </span>
          ))}
        </div>
        <div className="zoom-controls">
          <span className="zoom-hint">Scroll or pinch to zoom · drag to pan · double-click to reset</span>
          <button type="button" onClick={() => zoomAtCenter(1 / 1.5)} disabled={!zoomed} aria-label="Zoom out">
            −
          </button>
          <span className="zoom-level">{zoom < 10 ? zoom.toFixed(1) : Math.round(zoom)}×</span>
          <button type="button" onClick={() => zoomAtCenter(1.5)} aria-label="Zoom in">
            +
          </button>
          <button type="button" onClick={() => commit(null)} disabled={!zoomed}>
            Reset
          </button>
        </div>
      </div>

      <div
        ref={containerRef}
        className={`zoom-surface${zoomed ? ' zoomed' : ''}${dragging ? ' dragging' : ''}`}
        style={{ height, touchAction: zoomed ? 'none' : 'pan-y' }}
        tabIndex={0}
        role="application"
        aria-label="Zoomable chart. Plus and minus keys zoom, arrow keys pan, zero resets."
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onDoubleClick={() => commit(null)}
        onKeyDown={onKeyDown}
      >
        {width > 0 && current && (
          <LineChart width={width} height={height} data={visibleRows} margin={MARGIN}>
            <CartesianGrid stroke="#23283a" strokeDasharray="3 3" />
            <XAxis
              dataKey={xKey}
              type="number"
              domain={[current.x0, current.x1]}
              allowDataOverflow
              ticks={xTicks.map((tick) => tick.value)}
              interval={0}
              tickFormatter={(value: number) => xTickLabels.get(value) ?? ''}
              stroke="#7b839c"
              tick={{ fontSize: 11 }}
              tickMargin={angledTicks ? 10 : 8}
              angle={angledTicks ? -45 : 0}
              textAnchor={angledTicks ? 'end' : 'middle'}
              height={xAxisHeight}
              label={
                xLabel ? { value: xLabel, position: 'insideBottom', offset: 0, fill: '#7b839c' } : undefined
              }
            />
            <YAxis
              type="number"
              domain={[current.y0, current.y1]}
              allowDataOverflow
              ticks={yTicks}
              interval={0}
              tickFormatter={yTickFormatter}
              stroke="#7b839c"
              width={Y_AXIS_WIDTH}
              label={{ value: yLabel, angle: -90, position: 'insideLeft', fill: '#7b839c' }}
            />
            <ReferenceLine y={0} stroke="#4a5169" strokeWidth={2} />
            {!dragging && (
              <Tooltip
                isAnimationActive={false}
                content={(props: TooltipProps<number, string>) =>
                  cloneElement(tooltip, {
                    ...props,
                    payload: zoomed
                      ? props.payload?.filter(
                          (entry) =>
                            typeof entry.value === 'number' &&
                            entry.value >= current.y0 &&
                            entry.value <= current.y1,
                        )
                      : props.payload,
                  })
                }
              />
            )}
            {series.map((entry) => (
              <Line
                key={entry.key}
                type={lineType}
                dataKey={entry.key}
                name={entry.name}
                stroke={entry.color}
                strokeWidth={hovered === entry.key ? 3.5 : lineWidth}
                strokeOpacity={hovered && hovered !== entry.key ? 0.15 : 1}
                dot={false}
                activeDot={dragging ? false : renderActiveDot}
                isAnimationActive={false}
                connectNulls={connectNulls}
              />
            ))}
          </LineChart>
        )}

        {width > 0 && (
          <svg className="event-layer" width={width} height={height}>
            {labels.map((label) => (
              <g key={`label-${label.id}`} className="event-label">
                <line x1={label.px} y1={label.py} x2={label.cx} y2={label.y} stroke={label.color} strokeOpacity={0.7} />
                <rect
                  x={label.cx - label.textWidth / 2}
                  y={label.y - 9}
                  width={label.textWidth}
                  height={18}
                  rx={4}
                  fill="#11141d"
                  stroke={label.color}
                />
                <text x={label.cx} y={label.y + 4} textAnchor="middle">
                  {label.label}
                </text>
              </g>
            ))}
            {[...markers].reverse().map((marker) => (
              <g
                key={marker.id}
                className="event-marker"
                opacity={hovered && hovered !== marker.series ? 0.25 : 1}
                onPointerEnter={() => setHoveredEvent(marker.id)}
                onPointerLeave={() => setHoveredEvent(null)}
              >
                <Marker kind={marker.kind} x={marker.px} y={marker.py} color={marker.color} />
              </g>
            ))}
            {hoverLabel && !labels.some((label) => label.id === hoverLabel.id) && (
              <g className="event-label">
                <rect
                  x={Math.min(hoverLabel.px + 10, width - measureText(hoverLabel.label) - 24)}
                  y={hoverLabel.py - 30}
                  width={measureText(hoverLabel.label) + 14}
                  height={18}
                  rx={4}
                  fill="#11141d"
                  stroke={hoverLabel.color}
                />
                <text x={Math.min(hoverLabel.px + 17, width - measureText(hoverLabel.label) - 17)} y={hoverLabel.py - 17}>
                  {hoverLabel.label}
                </text>
              </g>
            )}
          </svg>
        )}

        {minimap && full && (
          <svg
            className="zoom-minimap"
            width={minimapSize.width}
            height={minimapSize.height}
            style={{ top: plot.top + 8, right: MARGIN.right + 8 }}
            onPointerDown={(event) => {
              event.currentTarget.setPointerCapture(event.pointerId)
              centerFromMinimap(event)
            }}
            onPointerMove={centerFromMinimap}
            onDoubleClick={(event) => event.stopPropagation()}
          >
            <MiniMapLines
              data={data}
              xKey={xKey}
              series={series}
              full={full}
              width={minimapSize.width}
              height={minimapSize.height}
              lineType={lineType}
            />
            <rect x={minimap.x} y={minimap.y} width={Math.max(2, minimap.w)} height={Math.max(2, minimap.h)} className="zoom-minimap-view" />
          </svg>
        )}
      </div>

      {hiddenCount > 0 && (
        <div className="zoom-footnote">
          Zoom in to reveal {hiddenCount} more event{hiddenCount === 1 ? '' : 's'} in this view.
        </div>
      )}
    </>
  )
}
