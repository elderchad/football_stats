import { useCallback, useEffect, useMemo, useState } from 'react'
import type { TooltipProps } from 'recharts'
import { fetchRecords, fetchSeasons, fetchTeams } from './api'
import type { RecordsResponse, Team, TeamGameMode } from './api'
import GameModeControl from './GameModeControl'
import ZoomChart, { numericTicks, stepTicks } from './ZoomChart'
import type { ChartEvent, ChartRow } from './ZoomChart'

const CONFERENCES = ['AFC', 'NFC'] as const

function buildChartData(records: RecordsResponse): ChartRow[] {
  const rows: ChartRow[] = [{ x: 0, label: 'Start', season: 0, week: 0 }]
  records.steps.forEach((step, index) => {
    rows.push({ x: index + 1, label: step.label, season: step.season, week: step.week })
  })

  for (const series of records.series) {
    const firstPlayed = series.values.findIndex((value) => value !== null)
    if (firstPlayed === -1) continue
    // Anchor every franchise on the baseline at the step before its first game.
    rows[firstPlayed][series.team] = 0
    series.values.forEach((value, index) => {
      if (value !== null) rows[index + 1][series.team] = value
    })
  }
  return rows
}

interface GameByGame {
  rows: ChartRow[]
  labels: Map<string, string[]>
  events: ChartEvent[]
}

/** Re-index every franchise by its own game count so all lines start at the left edge. */
function buildGameByGame(records: RecordsResponse): GameByGame {
  const labels = new Map<string, string[]>()
  const gameIndex = new Map<string, Map<number, [number, number]>>()
  const longest = Math.max(0, ...records.series.map((series) => series.game_steps?.length ?? 0))
  const rows: ChartRow[] = Array.from({ length: longest + 1 }, (_, game) => ({ game }))

  for (const series of records.series) {
    const steps = series.game_steps ?? []
    const results = series.game_results ?? []
    const teamLabels = ['Start']
    const bySeason = new Map<number, [number, number]>()
    let total = 0
    rows[0][series.team] = 0
    steps.forEach((step, index) => {
      total += results[index]
      rows[index + 1][series.team] = total
      teamLabels.push(records.steps[step].label)
      const season = records.steps[step].season
      const span = bySeason.get(season)
      bySeason.set(season, span ? [span[0], index] : [index, index])
    })
    labels.set(series.team, teamLabels)
    gameIndex.set(series.team, bySeason)
  }

  const events: ChartEvent[] = []
  for (const event of records.events) {
    const steps = records.series.find((series) => series.team === event.series)?.game_steps
    const span = gameIndex.get(event.series)?.get(records.steps[event.step].season)
    if (!steps || !span) continue
    // Snap to the team's last game at or before the event's step within that season.
    let index = span[0]
    for (let game = span[0]; game <= span[1] && steps[game] <= event.step; game += 1) index = game
    events.push({ ...event, x: index + 1 })
  }
  return { rows, labels, events }
}

interface GameTooltipProps extends TooltipProps<number, string> {
  labels?: Map<string, string[]>
}

function GameTooltip({ active, payload, label, labels }: GameTooltipProps) {
  if (!active || !payload?.length) return null
  const game = Number(label)
  const entries = [...payload]
    .filter((entry) => typeof entry.value === 'number')
    .sort((a, b) => (b.value as number) - (a.value as number))
  const shown = entries.slice(0, 12)

  return (
    <div className="tooltip">
      <div className="tooltip-title">Game {game} of franchise history</div>
      {shown.map((entry) => (
        <div key={entry.name} className="tooltip-row qb">
          <span className="swatch" style={{ background: entry.color }} />
          <span className="tooltip-team">{entry.name}</span>
          <span className="tooltip-when">{labels?.get(entry.dataKey as string)?.[game] ?? ''}</span>
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

function ChartTooltip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null
  const label = payload[0].payload?.label as string | undefined
  const entries = [...payload]
    .filter((entry) => typeof entry.value === 'number')
    .sort((a, b) => (b.value as number) - (a.value as number))
  const shown = entries.slice(0, 12)

  return (
    <div className="tooltip">
      <div className="tooltip-title">{label}</div>
      {shown.map((entry) => (
        <div key={entry.name} className="tooltip-row">
          <span className="swatch" style={{ background: entry.color }} />
          <span className="tooltip-team">{entry.name}</span>
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

export default function TeamChart() {
  const [teams, setTeams] = useState<Team[]>([])
  const [seasonList, setSeasonList] = useState<number[]>([])
  const [startSeason, setStartSeason] = useState<number | null>(null)
  const [endSeason, setEndSeason] = useState<number | null>(null)
  const [gameMode, setGameMode] = useState<TeamGameMode>('all')
  const [showDefunct, setShowDefunct] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [hovered, setHovered] = useState<string | null>(null)
  const [records, setRecords] = useState<RecordsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [resolution, setResolution] = useState<'season' | 'game'>('season')

  useEffect(() => {
    Promise.all([fetchTeams(), fetchSeasons()])
      .then(([teamList, seasons]) => {
        setTeams(teamList)
        setSeasonList(seasons.seasons)
        setSelected(
          new Set(teamList.filter((team) => !team.defunct).map((team) => team.abbr)),
        )
        setStartSeason(seasons.min)
        setEndSeason(seasons.max)
      })
      .catch((err: Error) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    if (startSeason === null || endSeason === null) return
    setLoading(true)
    fetchRecords(startSeason, endSeason, gameMode)
      .then((data) => {
        setRecords(data)
        setError(null)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [startSeason, endSeason, gameMode])

  const teamsByAbbr = useMemo(
    () => new Map(teams.map((team) => [team.abbr, team])),
    [teams],
  )
  const visibleTeams = useMemo(() => {
    if (startSeason === null || endSeason === null) return []
    const appearingTeams = new Set((records?.series ?? []).map((series) => series.team))
    return teams.filter(
      (team) =>
        (showDefunct || !team.defunct) &&
        team.games > 0 &&
        team.first_season <= endSeason &&
        team.last_season >= startSeason &&
        (gameMode !== 'superbowls' || appearingTeams.has(team.abbr)),
    )
  }, [teams, showDefunct, startSeason, endSeason, gameMode, records])
  const chartData = useMemo(() => (records ? buildChartData(records) : []), [records])
  const ticks = useCallback(
    (x0: number, x1: number, max: number) => stepTicks(chartData, x0, x1, max),
    [chartData],
  )
  const chartSeries = useMemo(
    () =>
      visibleTeams
        .filter((team) => selected.has(team.abbr))
        .map((team) => ({ key: team.abbr, name: team.abbr, color: team.color })),
    [visibleTeams, selected],
  )
  const events = useMemo<ChartEvent[]>(
    () => (records?.events ?? []).map((event) => ({ ...event, x: event.step + 1 })),
    [records],
  )
  const gameByGame = useMemo(
    () => (records && resolution === 'game' ? buildGameByGame(records) : null),
    [records, resolution],
  )

  const standings = useMemo(() => {
    if (!records) return []
    return [...records.series]
      .filter((series) => selected.has(series.team))
      .sort((a, b) => (b.final ?? 0) - (a.final ?? 0))
  }, [records, selected])

  const toggleTeam = (abbr: string) => {
    setSelected((previous) => {
      const next = new Set(previous)
      if (next.has(abbr)) next.delete(abbr)
      else next.add(abbr)
      return next
    })
  }

  const setAll = (value: boolean) =>
    setSelected(value ? new Set(visibleTeams.map((team) => team.abbr)) : new Set())

  return (
    <>
      <nav className="tabs sub resolution-tabs" role="tablist" aria-label="Time resolution">
        {([['season', 'Season timeline'], ['game', 'Game-by-game']] as const).map(([id, text]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={resolution === id}
            className={`tab${resolution === id ? ' active' : ''}`}
            onClick={() => setResolution(id)}
          >
            {text}
          </button>
        ))}
      </nav>

      <p className="lede">
        Each line starts at the baseline and steps <strong>+1</strong> for a win,
        <strong> &minus;1</strong> for a loss, and holds flat on a tie &mdash;{' '}
        {resolution === 'game'
          ? 'one step per game the franchise played. Lines are aligned at game one so franchises can be compared directly.'
          : 'one step per week of the season.'}
      </p>

      <section className="controls">
        <label>
          From season
          <select
            value={startSeason ?? ''}
            onChange={(event) => setStartSeason(Number(event.target.value))}
          >
            {seasonList.map((season) => (
              <option key={season} value={season}>
                {season}
              </option>
            ))}
          </select>
        </label>

        <label>
          To season
          <select
            value={endSeason ?? ''}
            onChange={(event) => setEndSeason(Number(event.target.value))}
          >
            {seasonList.map((season) => (
              <option key={season} value={season}>
                {season}
              </option>
            ))}
          </select>
        </label>

        <GameModeControl value={gameMode} onChange={setGameMode} includeSuperBowls />

        <label className="checkbox">
          <input
            type="checkbox"
            checked={showDefunct}
            onChange={(event) => setShowDefunct(event.target.checked)}
          />
          Show defunct franchises
        </label>

        <div className="button-group">
          <button type="button" onClick={() => setAll(true)}>
            All teams
          </button>
          <button type="button" onClick={() => setAll(false)}>
            None
          </button>
          {CONFERENCES.map((conference) => (
            <button
              key={conference}
              type="button"
              onClick={() =>
                setSelected(
                  new Set(
                    visibleTeams
                      .filter((team) => team.conference === conference)
                      .map((team) => team.abbr),
                  ),
                )
              }
            >
              {conference} only
            </button>
          ))}
        </div>
      </section>

      {error && <div className="error">Could not load data: {error}</div>}

      <section className="chart-card">
        {loading && <div className="status">Loading NFL results&hellip;</div>}
        {gameByGame ? (
          <ZoomChart
            data={gameByGame.rows}
            xKey="game"
            series={chartSeries}
            ticks={numericTicks}
            tooltip={<GameTooltip labels={gameByGame.labels} />}
            xLabel="Games into franchise history"
            yLabel="Cumulative wins − losses"
            events={gameByGame.events}
            hovered={hovered}
            lineWidth={1.6}
          />
        ) : (
          <ZoomChart
            data={chartData}
            xKey="x"
            series={chartSeries}
            ticks={ticks}
            tooltip={<ChartTooltip />}
            yLabel="Cumulative wins − losses"
            events={events}
            hovered={hovered}
            connectNulls
            angledTicks
            lineWidth={1.6}
          />
        )}
      </section>

      <section className="teams">
        {visibleTeams.map((team) => {
          const isOn = selected.has(team.abbr)
          return (
            <button
              key={team.abbr}
              type="button"
              className={`team-chip${isOn ? '' : ' off'}`}
              style={{ borderColor: team.color }}
              onClick={() => toggleTeam(team.abbr)}
              onMouseEnter={() => setHovered(team.abbr)}
              onMouseLeave={() => setHovered(null)}
            >
              <span className="swatch" style={{ background: team.color }} />
              {team.abbr}
            </button>
          )
        })}
        <button type="button" className="chip-action" onClick={() => setAll(true)}>
          Select All
        </button>
        <button type="button" className="chip-action" onClick={() => setAll(false)}>
          Deselect All
        </button>
      </section>

      {standings.length > 0 && (
        <section className="standings">
          <h2>
            Net record, {records?.start_season}&ndash;{records?.end_season}
          </h2>
          <table>
            <thead>
              <tr>
                <th>Team</th>
                <th>GP</th>
                <th>W</th>
                <th>L</th>
                <th>T</th>
                <th>Net</th>
              </tr>
            </thead>
            <tbody>
              {standings.map((series) => (
                <tr
                  key={series.team}
                  onMouseEnter={() => setHovered(series.team)}
                  onMouseLeave={() => setHovered(null)}
                >
                  <td>
                    <span
                      className="swatch"
                      style={{ background: teamsByAbbr.get(series.team)?.color }}
                    />
                    {teamsByAbbr.get(series.team)?.name ?? series.team}
                  </td>
                  <td>{series.wins + series.losses + series.ties}</td>
                  <td>{series.wins}</td>
                  <td>{series.losses}</td>
                  <td>{series.ties}</td>
                  <td className={(series.final ?? 0) >= 0 ? 'pos' : 'neg'}>
                    {(series.final ?? 0) > 0 ? `+${series.final}` : series.final}
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
