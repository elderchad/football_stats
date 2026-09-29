import { useEffect, useMemo, useState } from 'react'
import type { TooltipProps } from 'recharts'
import { fetchQbRecords, fetchQuarterbacks } from './api'
import type { GameMode, QbRecordsResponse, Quarterback } from './api'
import GameModeControl from './GameModeControl'
import ZoomChart, { numericTicks } from './ZoomChart'
import type { ChartEvent } from './ZoomChart'

type ChartRow = Record<string, number>

function buildChartData(records: QbRecordsResponse): ChartRow[] {
  const rows: ChartRow[] = Array.from({ length: records.max_steps }, (_, step) => ({ step }))
  for (const series of records.series) {
    series.values.forEach((value, index) => {
      rows[index][series.id] = value
    })
  }
  return rows
}

interface QbTooltipProps extends TooltipProps<number, string> {
  labels?: Map<string, string[]>
}

function QbTooltip({ active, payload, label, labels }: QbTooltipProps) {
  if (!active || !payload?.length) return null
  const step = Number(label)
  const entries = [...payload]
    .filter((entry) => typeof entry.value === 'number')
    .sort((a, b) => (b.value as number) - (a.value as number))
  const shown = entries.slice(0, 12)

  return (
    <div className="tooltip">
      <div className="tooltip-title">Game {step} of career</div>
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

export default function QbChart() {
  const [quarterbacks, setQuarterbacks] = useState<Quarterback[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [gameMode, setGameMode] = useState<GameMode>('all')
  const [hovered, setHovered] = useState<string | null>(null)
  const [records, setRecords] = useState<QbRecordsResponse | null>(null)
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
      setRecords({ series: [], max_steps: 0, game_mode: gameMode })
      setLoading(false)
      return
    }
    setLoading(true)
    fetchQbRecords([...selected], gameMode)
      .then((data) => {
        setRecords(data)
        setError(null)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [selected, gameMode])

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
  const qbById = useMemo(
    () => new Map(quarterbacks.map((qb) => [qb.id, qb])),
    [quarterbacks],
  )

  const toggleQb = (id: string) =>
    setSelected((previous) => {
      const next = new Set(previous)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const truncated = quarterbacks.filter((qb) => selected.has(qb.id) && qb.truncated)

  return (
    <>
      <p className="lede">
        Every quarterback starts at the baseline in his first NFL season. The line steps
        <strong> +1</strong> for a win, <strong>&minus;1</strong> for a loss and holds flat
        on a tie, following <strong>his team&apos;s</strong> results for every week of his
        career. Lines are aligned at game one so careers can be compared directly.
      </p>

      <section className="controls">
        <GameModeControl value={gameMode} onChange={setGameMode} includeSuperBowls />

        <div className="button-group">
          <button
            type="button"
            onClick={() => setSelected(new Set(quarterbacks.map((qb) => qb.id)))}
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
                new Set(
                  quarterbacks.filter((qb) => qb.status === 'hof').map((qb) => qb.id),
                ),
              )
            }
          >
            Hall of Fame only
          </button>
          <button
            type="button"
            onClick={() =>
              setSelected(
                new Set(
                  quarterbacks.filter((qb) => qb.last_season >= 2024).map((qb) => qb.id),
                ),
              )
            }
          >
            Active only
          </button>
        </div>
      </section>

      {error && <div className="error">Could not load data: {error}</div>}

      <section className="chart-card">
        {loading && <div className="status">Loading careers&hellip;</div>}
        <ZoomChart
          data={chartData}
          xKey="step"
          series={chartSeries}
          ticks={numericTicks}
          tooltip={<QbTooltip labels={labelMap} />}
          xLabel="Games into career"
          yLabel="Cumulative wins − losses"
          events={events}
          hovered={hovered}
        />
      </section>

      <section className="teams">
        {quarterbacks.map((qb) => (
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
            <span className="chip-meta">&rsquo;{String(qb.entered).slice(2)}</span>
          </button>
        ))}
        <button
          type="button"
          className="chip-action"
          onClick={() => setSelected(new Set(quarterbacks.map((qb) => qb.id)))}
        >
          Select All
        </button>
        <button
          type="button"
          className="chip-action"
          onClick={() => setSelected(new Set())}
        >
          Deselect All
        </button>
      </section>

      {truncated.length > 0 && (
        <p className="note">
          Play-by-play coverage begins in 1999, so{' '}
          {truncated.map((qb) => qb.name).join(', ')} start from their 1999 season rather
          than their true rookie year.
        </p>
      )}

      {ranking.length > 0 && (
        <section className="standings">
          <h2>Career team record</h2>
          <table>
            <thead>
              <tr>
                <th>Quarterback</th>
                <th>Seasons</th>
                <th>Teams</th>
                <th>GP</th>
                <th>W</th>
                <th>L</th>
                <th>T</th>
                <th>Net</th>
              </tr>
            </thead>
            <tbody>
              {ranking.map((series) => {
                const qb = qbById.get(series.id)
                return (
                  <tr
                    key={series.id}
                    onMouseEnter={() => setHovered(series.id)}
                    onMouseLeave={() => setHovered(null)}
                  >
                    <td>
                      <span className="swatch" style={{ background: series.color }} />
                      {series.name}
                    </td>
                    <td>
                      {qb?.first_season}&ndash;{qb?.last_season}
                    </td>
                    <td>
                      {[...new Set(qb?.teams.map((stint) => stint.team) ?? [])].join(', ')}
                    </td>
                    <td>{series.wins + series.losses + series.ties}</td>
                    <td>{series.wins}</td>
                    <td>{series.losses}</td>
                    <td>{series.ties}</td>
                    <td className={series.final >= 0 ? 'pos' : 'neg'}>
                      {series.final > 0 ? `+${series.final}` : series.final}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </section>
      )}
    </>
  )
}
