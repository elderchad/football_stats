import { useCallback, useEffect, useMemo, useState } from 'react'
import type { TooltipProps } from 'recharts'
import {
  fetchNcaafRecords,
  fetchNcaafRivalries,
  fetchNcaafSeasons,
  fetchNcaafTeams,
} from './api'
import type {
  NcaafGameMode,
  NcaafRecordsResponse,
  NcaafRivalry,
  NcaafTeam,
} from './api'
import NcaafModeControl from './NcaafModeControl'
import useSelection from './useSelection'
import NcaafRankings from './NcaafRankings'
import ZoomChart, { stepTicks } from './ZoomChart'
import type { ChartEvent, ChartRow } from './ZoomChart'

function buildChartData(records: NcaafRecordsResponse): ChartRow[] {
  const rows: ChartRow[] = [{ x: 0, label: 'Start', season: 0, week: 0 }]
  records.steps.forEach((step, index) => {
    rows.push({ x: index + 1, label: step.label, season: step.season, week: step.week })
  })
  for (const series of records.series) {
    rows[0][series.team] = 0
    series.values.forEach((value, index) => {
      rows[index + 1][series.team] = value
    })
  }
  return rows
}

function NcaafTooltip({ active, payload }: TooltipProps<number, string>) {
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
            <span className="tooltip-value">
              {(entry.value as number) > 0 ? `+${entry.value}` : entry.value}
            </span>
          </div>
        ))}
    </div>
  )
}

export default function NcaafChart() {
  const [rivalries, setRivalries] = useState<NcaafRivalry[]>([])
  const [rivalryId, setRivalryId] = useState('holy-war')
  const [teams, setTeams] = useState<NcaafTeam[]>([])
  const [seasons, setSeasons] = useState<number[]>([])
  const [startSeason, setStartSeason] = useState<number | null>(null)
  const [endSeason, setEndSeason] = useState<number | null>(null)
  const [gameMode, setGameMode] = useState<NcaafGameMode>('all')
  const { selected, setSelected, initializeSelection } = useSelection(`ncaaf-selection-${rivalryId}`)
  const [hovered, setHovered] = useState<string | null>(null)
  const [records, setRecords] = useState<NcaafRecordsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<'record' | 'rankings'>('record')

  useEffect(() => {
    fetchNcaafRivalries()
      .then(setRivalries)
      .catch((err: Error) => setError(err.message))
  }, [])

  useEffect(() => {
    setLoading(true)
    setTeams([])
    setRecords(null)
    setStartSeason(null)
    setEndSeason(null)
    Promise.all([fetchNcaafTeams(rivalryId), fetchNcaafSeasons(rivalryId)])
      .then(([teamList, seasonData]) => {
        setTeams(teamList)
        setSeasons(seasonData.seasons)
        initializeSelection(new Set(teamList.map((team) => team.abbr)))
        setStartSeason(seasonData.min)
        setEndSeason(seasonData.max)
      })
      .catch((err: Error) => {
        setError(err.message)
        setLoading(false)
      })
  }, [rivalryId])

  useEffect(() => {
    if (startSeason === null || endSeason === null) return
    setLoading(true)
    fetchNcaafRecords(startSeason, endSeason, gameMode, rivalryId)
      .then((data) => {
        setRecords(data)
        setError(null)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [startSeason, endSeason, gameMode, rivalryId])

  const teamMap = useMemo(() => new Map(teams.map((team) => [team.abbr, team])), [teams])
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
  const events = useMemo<ChartEvent[]>(
    () => (records?.events ?? []).map((event) => ({ ...event, x: event.step + 1 })),
    [records],
  )
  const standings = useMemo(
    () =>
      [...(records?.series ?? [])]
        .filter((series) => selected.has(series.team))
        .sort((a, b) => (b.final ?? 0) - (a.final ?? 0)),
    [records, selected],
  )
  const rivalry = rivalries.find((entry) => entry.id === rivalryId)

  const toggleTeam = (team: string) =>
    setSelected((previous) => {
      const next = new Set(previous)
      if (next.has(team)) next.delete(team)
      else next.add(team)
      return next
    })

  const chips = (
    <section className="teams">
      {teams.map((team) => (
        <button
          key={team.abbr}
          type="button"
          className={`team-chip${selected.has(team.abbr) ? '' : ' off'}`}
          style={{ borderColor: team.color }}
          onClick={() => toggleTeam(team.abbr)}
          onMouseEnter={() => setHovered(team.abbr)}
          onMouseLeave={() => setHovered(null)}
        >
          <span className="swatch" style={{ background: team.color }} />
          {team.name}
        </button>
      ))}
      <button type="button" className="chip-action" onClick={() => setSelected(new Set(teams.map((team) => team.abbr)))}>
        Select All
      </button>
      <button type="button" className="chip-action" onClick={() => setSelected(new Set())}>
        Deselect All
      </button>
    </section>
  )

  return (
    <>
      <div className="section-heading">
        <div>
          <h2>{rivalry?.name ?? 'College Football Rivalry'}</h2>
          <p className="lede">
            {view === 'rankings'
              ? 'Weekly AP Poll position for both programs. The top of the chart is #1 and the bottom is unranked, so a rising line is a team climbing the poll.'
              : gameMode === 'head_to_head'
                ? 'Only direct meetings count. The winner steps +1, the loser −1, and a tie stays flat.'
                : 'A direct program comparison. Each line steps +1 for a win, −1 for a loss, and stays flat for a tie.'}
          </p>
        </div>
        <span className="rivalry-mark">{rivalry?.nickname ?? 'Rivalry'}</span>
      </div>

      <nav className="tabs sub resolution-tabs" role="tablist" aria-label="College view">
        {([['record', 'Win–loss walk'], ['rankings', 'AP rankings']] as const).map(([id, text]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={view === id}
            className={`tab${view === id ? ' active' : ''}`}
            onClick={() => setView(id)}
          >
            {text}
          </button>
        ))}
      </nav>

      <section className="controls">
        <label>
          Rivalry
          <select value={rivalryId} onChange={(event) => setRivalryId(event.target.value)}>
            {rivalries.map((entry) => (
              <option key={entry.id} value={entry.id}>{entry.name}</option>
            ))}
          </select>
        </label>
        <label>
          From season
          <select value={startSeason ?? ''} onChange={(event) => setStartSeason(Number(event.target.value))}>
            {seasons.map((season) => <option key={season}>{season}</option>)}
          </select>
        </label>
        <label>
          To season
          <select value={endSeason ?? ''} onChange={(event) => setEndSeason(Number(event.target.value))}>
            {seasons.map((season) => <option key={season}>{season}</option>)}
          </select>
        </label>
        {view === 'record' && <NcaafModeControl value={gameMode} onChange={setGameMode} />}
        <div className="button-group">
          <button type="button" onClick={() => setSelected(new Set(teams.map((team) => team.abbr)))}>All teams</button>
          <button type="button" onClick={() => setSelected(new Set())}>None</button>
        </div>
      </section>

      {error && <div className="error">Could not load data: {error}</div>}

      {view === 'rankings' ? (
        <NcaafRankings
          rivalryId={rivalryId}
          teams={teams}
          selected={selected}
          hovered={hovered}
          onHover={setHovered}
          chips={chips}
          startSeason={startSeason}
          endSeason={endSeason}
        />
      ) : (
        <>
          <section className="chart-card rivalry-chart">
            {loading && <div className="status">Loading college results&hellip;</div>}
            <ZoomChart
              data={chartData}
              xKey="x"
              series={chartSeries}
              ticks={ticks}
              tooltip={<NcaafTooltip />}
              yLabel="Cumulative wins − losses"
              events={events}
              hovered={hovered}
              angledTicks
              lineWidth={2.4}
            />
          </section>

          {chips}

          <section className="standings">
        <h2>
          {gameMode === 'head_to_head' ? 'Head-to-head record' : 'Program record'}, {' '}
          {records?.start_season}&ndash;{records?.end_season}
        </h2>
        <table>
          <thead><tr><th>Team</th><th>GP</th><th>W</th><th>L</th><th>T</th><th>Net</th></tr></thead>
          <tbody>
            {standings.map((series) => (
              <tr key={series.team} onMouseEnter={() => setHovered(series.team)} onMouseLeave={() => setHovered(null)}>
                <td><span className="swatch" style={{ background: teamMap.get(series.team)?.color }} />{teamMap.get(series.team)?.name}</td>
                <td>{series.wins + series.losses + series.ties}</td>
                <td>{series.wins}</td><td>{series.losses}</td><td>{series.ties}</td>
                <td className={(series.final ?? 0) >= 0 ? 'pos' : 'neg'}>{(series.final ?? 0) > 0 ? `+${series.final}` : series.final}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <p className="note coverage-note">
        Pre-2001 results are game-by-game from James Howell&apos;s historical scores database;
        the few seasons it does not cover (mostly before 1905) appear as a single season-total
        step. 2001 onward is game-by-game cfbfastR data. Head to Head uses published rivalry
        results before 2001 and game-level results thereafter. See the Data audit tab for
        coverage and cross-source checks.
      </p>
        </>
      )}
    </>
  )
}
