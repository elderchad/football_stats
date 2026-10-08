import { useEffect, useMemo, useState } from 'react'
import type { TooltipProps } from 'recharts'
import { fetchQbTimeline, fetchQuarterbacks } from './api'
import type { GameMode, QbTimelineMetric, QbTimelineResponse, Quarterback } from './api'
import GameModeControl from './GameModeControl'
import useSelection from './useSelection'
import ZoomChart, { numericTicks } from './ZoomChart'
import type { ChartEvent } from './ZoomChart'

type ChartRow = { season: number } & Record<string, number | null>

const METRIC_LABELS: Record<QbTimelineMetric, string> = {
  games: 'Cumulative starting QB wins − losses',
  td: 'Cumulative passing TDs',
  int: 'Cumulative interceptions',
  td_int: 'Cumulative passing TD − INT',
}

function buildChartData(records: QbTimelineResponse): ChartRow[] {
  const annualRows = records.seasons.map((season, index) => {
    const row: ChartRow = { season }
    for (const series of records.series) {
      row[series.id] = series.values[index]
    }
    return row
  })
  for (const series of records.series) {
    if (series.first_season === null) continue
    const baselineIndex = series.first_season - records.seasons[0] - 1
    if (baselineIndex >= 0) annualRows[baselineIndex][series.id] = 0
  }
  return annualRows
}

function TimelineTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null
  const entries = [...payload]
    .filter((entry) => typeof entry.value === 'number')
    .sort((a, b) => Math.abs(b.value as number) - Math.abs(a.value as number))

  return (
    <div className="tooltip">
      <div className="tooltip-title">Through the end of the {label} season</div>
      {entries.slice(0, 12).map((entry) => (
        <div key={entry.dataKey as string} className="tooltip-row qb">
          <span className="swatch" style={{ background: entry.color }} />
          <span className="tooltip-team">{entry.name}</span>
          <span />
          <span className="tooltip-value">
            {(entry.value as number) > 0 ? `+${entry.value}` : entry.value}
          </span>
        </div>
      ))}
      {entries.length > 12 && <div className="tooltip-more">+{entries.length - 12} more</div>}
    </div>
  )
}

interface Props {
  metric: QbTimelineMetric
}

export default function QbTimeline({ metric }: Props) {
  const [quarterbacks, setQuarterbacks] = useState<Quarterback[]>([])
  const { selected, setSelected, initializeSelection } = useSelection('qb-selection')
  const [gameMode, setGameMode] = useState<GameMode>('all')
  const [hovered, setHovered] = useState<string | null>(null)
  const [records, setRecords] = useState<QbTimelineResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchQuarterbacks()
      .then((list) => {
        setQuarterbacks(list)
        initializeSelection(new Set(list.map((qb) => qb.id)))
      })
      .catch((err: Error) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    if (selected.size === 0) {
      setRecords((previous) => (previous ? { ...previous, series: [] } : null))
      setLoading(false)
      return
    }
    setLoading(true)
    fetchQbTimeline([...selected], gameMode, metric)
      .then((data) => {
        setRecords(data)
        setError(null)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [selected, gameMode, metric])

  const chartData = useMemo(() => (records ? buildChartData(records) : []), [records])
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

  const toggleQb = (id: string) =>
    setSelected((previous) => {
      const next = new Set(previous)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const description =
    metric === 'games'
      ? 'Each season adds wins minus losses in games that quarterback started to a running total.'
      : metric === 'td'
        ? 'Each season adds the quarterback’s passing touchdowns to a running total.'
        : metric === 'int'
          ? 'Each season adds the quarterback’s interceptions to a running total.'
          : 'Each season adds passing touchdowns minus interceptions to a running total.'

  return (
    <>
      <p className="lede">
        Each line starts at zero. {description} The x-axis is the full NFL timeline; each
        point is the running total through the end of its labelled season.
      </p>
      {metric === 'games' && (
        <p className="note">Starter names are available from 1950. Earlier starts are not inferred.</p>
      )}

      <section className="controls">
        <GameModeControl value={gameMode} onChange={setGameMode} includeSuperBowls />
        <div className="button-group">
          <button type="button" onClick={() => setSelected(new Set(quarterbacks.map((qb) => qb.id)))}>
            All QBs
          </button>
          <button type="button" onClick={() => setSelected(new Set())}>
            None
          </button>
          <button
            type="button"
            onClick={() =>
              setSelected(new Set(quarterbacks.filter((qb) => qb.status === 'hof').map((qb) => qb.id)))
            }
          >
            Hall of Fame only
          </button>
        </div>
      </section>

      {error && <div className="error">Could not load data: {error}</div>}

      <section className="chart-card">
        {loading && <div className="status">Loading season timeline&hellip;</div>}
        <ZoomChart
          data={chartData}
          xKey="season"
          series={chartSeries}
          ticks={numericTicks}
          tooltip={<TimelineTooltip />}
          xLabel="NFL season"
          yLabel={METRIC_LABELS[metric]}
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
          </button>
        ))}
        <button type="button" className="chip-action" onClick={() => setSelected(new Set(quarterbacks.map((qb) => qb.id)))}>
          Select All
        </button>
        <button type="button" className="chip-action" onClick={() => setSelected(new Set())}>
          Deselect All
        </button>
      </section>

      {metric !== 'games' && (
        <p className="note">
          Per-game passing stats start in {records?.stats_start_season ?? 1999}. Earlier career
          seasons are blank because those stats are not available.
        </p>
      )}
    </>
  )
}
