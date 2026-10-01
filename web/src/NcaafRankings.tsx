import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { TooltipProps } from 'recharts'
import { fetchNcaafRankings } from './api'
import type { NcaafRankingsResponse, NcaafTeam } from './api'
import ZoomChart, { stepTicks } from './ZoomChart'
import type { ChartRow } from './ZoomChart'

interface Props {
  rivalryId: string
  teams: NcaafTeam[]
  selected: Set<string>
  hovered: string | null
  onHover: (team: string | null) => void
  chips?: ReactNode
  startSeason: number | null
  endSeason: number | null
}

const rankLabel = (value: number, size: number) => {
  if (value < 0 || value > size) return ''
  return value === 0 ? 'Unranked' : `#${size + 1 - value}`
}

function buildChartData(records: NcaafRankingsResponse): ChartRow[] {
  return records.steps.map((step, index) => {
    const row: ChartRow = { x: index, label: step.label, season: step.season, week: step.week }
    for (const series of records.series) row[series.team] = series.values[index]
    return row
  })
}

interface RankTooltipProps extends TooltipProps<number, string> {
  size: number
}

function RankTooltip({ active, payload, size }: RankTooltipProps) {
  if (!active || !payload?.length) return null
  const label = payload[0].payload?.label as string | undefined
  return (
    <div className="tooltip">
      <div className="tooltip-title">{label}</div>
      {[...payload]
        .filter((entry) => typeof entry.value === 'number')
        .sort((a, b) => (b.value as number) - (a.value as number))
        .map((entry) => (
          <div key={entry.dataKey as string} className="tooltip-row">
            <span className="swatch" style={{ background: entry.color }} />
            <span className="tooltip-team">{entry.name}</span>
            <span className="tooltip-value">{rankLabel(entry.value as number, size)}</span>
          </div>
        ))}
    </div>
  )
}

export default function NcaafRankings({
  rivalryId,
  teams,
  selected,
  hovered,
  onHover,
  chips,
  startSeason,
  endSeason,
}: Props) {
  const [records, setRecords] = useState<NcaafRankingsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setRecords(null)
    fetchNcaafRankings(rivalryId, startSeason ?? undefined, endSeason ?? undefined)
      .then((data) => {
        setRecords(data)
        setError(null)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [rivalryId, startSeason, endSeason])

  const chartData = useMemo(() => (records ? buildChartData(records) : []), [records])
  const ticks = useCallback(
    (x0: number, x1: number, max: number) => stepTicks(chartData, x0, x1, max),
    [chartData],
  )
  const chartSeries = useMemo(
    () =>
      teams
        .filter((team) => selected.has(team.abbr))
        .map((team) => ({ key: team.abbr, name: team.name, color: team.color })),
    [teams, selected],
  )
  const size = records?.poll_size ?? 25
  const teamMap = useMemo(() => new Map(teams.map((team) => [team.abbr, team])), [teams])

  return (
    <>
      {error && <div className="error">Could not load rankings: {error}</div>}

      <section className="chart-card rivalry-chart">
        {loading && <div className="status">Loading AP Poll history&hellip;</div>}
        <ZoomChart
          data={chartData}
          xKey="x"
          series={chartSeries}
          ticks={ticks}
          tooltip={<RankTooltip size={size} />}
          yLabel={`${records?.poll ?? 'AP'} Poll position`}
          yBounds={[0, 50]}
          yTickFormatter={(value) => rankLabel(value, size)}
          hovered={hovered}
          angledTicks
          lineWidth={2.2}
          lineType="stepAfter"
        />
      </section>

      {chips}

      {records && (
        <section className="standings">
          <h2>
            Poll history, {records.start_season}&ndash;{records.end_season}
          </h2>
          <table>
            <thead>
              <tr>
                <th>Team</th>
                <th>Polls</th>
                <th>Ranked</th>
                <th>% ranked</th>
                <th>Best</th>
                <th>Weeks at #1</th>
                <th>Now</th>
              </tr>
            </thead>
            <tbody>
              {[...records.series]
                .sort((a, b) => b.ranked - a.ranked)
                .map((series) => (
                  <tr
                    key={series.team}
                    onMouseEnter={() => onHover(series.team)}
                    onMouseLeave={() => onHover(null)}
                  >
                    <td>
                      <span
                        className="swatch"
                        style={{ background: teamMap.get(series.team)?.color }}
                      />
                      {teamMap.get(series.team)?.name ?? series.team}
                    </td>
                    <td>{series.polls}</td>
                    <td>{series.ranked}</td>
                    <td>{Math.round((series.ranked / Math.max(1, series.polls)) * 100)}%</td>
                    <td>{series.best ? `#${series.best}` : '\u2014'}</td>
                    <td>{series.weeks_at_1}</td>
                    <td>{rankLabel(series.final, size)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </section>
      )}

      <p className="note coverage-note">
        Weekly {records?.poll ?? 'AP'} Poll positions come from the per-season Wikipedia rankings
        articles. The poll began in {records?.first_poll_season ?? 1936}, was not released every week
        in the early years, and only ranked a top 20 for much of its history &mdash; teams ranked
        21&ndash;25 in those seasons therefore show as unranked.
      </p>
    </>
  )
}
