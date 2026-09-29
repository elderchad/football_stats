import { useEffect, useMemo, useState } from 'react'
import type { TooltipProps } from 'recharts'
import { fetchQbTdInt, fetchQuarterbacks } from './api'
import type { GameMode, QbTdIntResponse, Quarterback } from './api'
import GameModeControl from './GameModeControl'
import ZoomChart, { numericTicks } from './ZoomChart'
import type { ChartEvent } from './ZoomChart'

type ChartRow = Record<string, number>

function buildChartData(records: QbTdIntResponse): ChartRow[] {
  const rows: ChartRow[] = Array.from({ length: records.max_steps }, (_, step) => ({ step }))
  for (const series of records.series) {
    series.values.forEach((value, index) => {
      rows[index][series.id] = value
    })
  }
  return rows
}

interface TdIntTooltipProps extends TooltipProps<number, string> {
  labels?: Map<string, string[]>
}

function TdIntTooltip({ active, payload, label, labels }: TdIntTooltipProps) {
  if (!active || !payload?.length) return null
  const step = Number(label)
  const entries = [...payload]
    .filter((entry) => typeof entry.value === 'number')
    .sort((a, b) => (b.value as number) - (a.value as number))
  const shown = entries.slice(0, 12)

  return (
    <div className="tooltip">
      <div className="tooltip-title">Game {step}</div>
      {shown.map((entry) => (
        <div key={entry.dataKey as string} className="tooltip-row qb">
          <span className="swatch" style={{ background: entry.color }} />
          <span className="tooltip-team">{entry.name}</span>
          <span className="tooltip-when">
            {labels?.get(entry.dataKey as string)?.[step] ?? ''}
          </span>
          <span className="tooltip-value">
            {(entry.value as number) > 0 ? `+${entry.value}` : entry.value}
          </span>
        </div>
      ))}
      {entries.length > shown.length && (
        <div className="tooltip-more">+{entries.length - shown.length} more</div>
      )}
    </div>
  )
}

interface Props {
  metric: 'td' | 'int' | 'td_int'
}

export default function QbTdIntChart({ metric }: Props) {
  const [quarterbacks, setQuarterbacks] = useState<Quarterback[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [gameMode, setGameMode] = useState<GameMode>('all')
  const [hovered, setHovered] = useState<string | null>(null)
  const [records, setRecords] = useState<QbTdIntResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchQuarterbacks()
      .then((list) => {
        setQuarterbacks(list)
        setSelected(new Set(list.map((qb) => qb.id)))
      })
      .catch((err: Error) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    if (selected.size === 0) {
      setRecords((previous) =>
        previous ? { ...previous, series: [], max_steps: 0 } : null,
      )
      setLoading(false)
      return
    }
    setLoading(true)
    fetchQbTdInt([...selected], gameMode, metric)
      .then((data) => {
        setRecords(data)
        setError(null)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [selected, gameMode, metric])

  const chartData = useMemo(() => (records ? buildChartData(records) : []), [records])
  const labelMap = useMemo(
    () => new Map((records?.series ?? []).map((series) => [series.id, series.labels])),
    [records],
  )
  const chartSeries = useMemo(
    () => (records?.series ?? []).map((series) => ({ key: series.id, name: series.name, color: series.color })),
    [records],
  )
  const events = useMemo<ChartEvent[]>(
    () =>
      (records?.series ?? []).flatMap((series) =>
        series.events.map((event) => ({ ...event, series: series.id })),
      ),
    [records],
  )
  const ranking = useMemo(
    () => [...(records?.series ?? [])].sort((a, b) => b.final - a.final),
    [records],
  )

  // Passing stats only exist from 1999, so pre-1999 careers cannot be charted here.
  const withStats = useMemo(
    () => new Set((records?.series ?? []).map((series) => series.id)),
    [records],
  )
  const available = useMemo(
    () =>
      quarterbacks.filter(
        (qb) => withStats.has(qb.id) || qb.last_season >= (records?.stats_start_season ?? 1999),
      ),
    [quarterbacks, withStats, records],
  )

  const toggleQb = (id: string) =>
    setSelected((previous) => {
      const next = new Set(previous)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <>
      <p className="lede">
        Each line starts at zero and moves by{' '}
        <strong>
          {metric === 'td' && 'passing touchdowns'}
          {metric === 'int' && 'interceptions'}
          {metric === 'td_int' && 'passing touchdowns minus interceptions'}
        </strong>{' '}
        in every game the quarterback played. Lines are aligned at game one so careers can
        be compared directly.
      </p>

      <section className="controls">
        <GameModeControl value={gameMode} onChange={setGameMode} includeSuperBowls />

        <div className="button-group">
          <button
            type="button"
            onClick={() => setSelected(new Set(available.map((qb) => qb.id)))}
          >
            All QBs
          </button>
          <button type="button" onClick={() => setSelected(new Set())}>
            None
          </button>
          <button
            type="button"
            onClick={() =>
              setSelected(
                new Set(available.filter((qb) => qb.last_season >= 2024).map((qb) => qb.id)),
              )
            }
          >
            Active only
          </button>
        </div>
      </section>

      {error && <div className="error">Could not load data: {error}</div>}

      <section className="chart-card">
        {loading && <div className="status">Loading passing stats&hellip;</div>}
        <ZoomChart
          data={chartData}
          xKey="step"
          series={chartSeries}
          ticks={numericTicks}
          tooltip={<TdIntTooltip labels={labelMap} />}
          xLabel="Games played"
          yLabel={
            metric === 'td'
              ? 'Cumulative passing TDs'
              : metric === 'int'
                ? 'Cumulative interceptions'
                : 'Cumulative TD − INT'
          }
          events={events}
          hovered={hovered}
        />
      </section>

      <section className="teams">
        {available.map((qb) => (
          <button
            key={qb.id}
            type="button"
            className={`team-chip qb${selected.has(qb.id) ? '' : ' off'}`}
            style={{ borderColor: qb.color }}
            onClick={() => toggleQb(qb.id)}
            onMouseEnter={() => setHovered(qb.id)}
            onMouseLeave={() => setHovered(null)}
          >
            <span className="swatch" style={{ background: qb.color }} />
            {qb.name}
          </button>
        ))}
        <button
          type="button"
          className="chip-action"
          onClick={() => setSelected(new Set(available.map((qb) => qb.id)))}
        >
          Select All
        </button>
        <button type="button" className="chip-action" onClick={() => setSelected(new Set())}>
          Deselect All
        </button>
      </section>

      <p className="note">
        Per-game passing stats only exist from {records?.stats_start_season ?? 1999}, so
        quarterbacks who retired before then are not shown, and careers that began earlier
        (Favre, Marino, Young&hellip;) are charted from {records?.stats_start_season ?? 1999}{' '}
        onwards.
      </p>

      {ranking.length > 0 && (
        <section className="standings">
          <h2>
            {metric === 'td'
              ? 'Career passing touchdowns'
              : metric === 'int'
                ? 'Career interceptions'
                : 'Career passing differential'}
          </h2>
          <table>
            <thead>
              <tr>
                <th>Quarterback</th>
                <th>From</th>
                <th>GP</th>
                <th>TD</th>
                <th>INT</th>
                <th>Final</th>
              </tr>
            </thead>
            <tbody>
              {ranking.map((series) => (
                <tr
                  key={series.id}
                  onMouseEnter={() => setHovered(series.id)}
                  onMouseLeave={() => setHovered(null)}
                >
                  <td>
                    <span className="swatch" style={{ background: series.color }} />
                    {series.name}
                  </td>
                  <td>{series.first_season}</td>
                  <td>{series.games}</td>
                  <td>{series.touchdowns}</td>
                  <td>{series.interceptions}</td>
                  <td className={series.final >= 0 ? 'pos' : 'neg'}>
                    {series.final > 0 ? `+${series.final}` : series.final}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  )
}
