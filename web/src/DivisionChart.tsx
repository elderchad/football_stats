import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { TooltipProps } from 'recharts'
import type { RecordsResponse, Team } from './api'

const DIVISION_ORDER = ['East', 'North', 'South', 'West']
const CONFERENCE_COLORS: Record<string, string> = { AFC: '#d50a0a', NFC: '#3b6fd8' }

interface DivisionTeam {
  abbr: string
  name: string
  color: string
  wins: number
  losses: number
  ties: number
  net: number
}

interface Division {
  name: string
  conference: string
  wins: number
  losses: number
  ties: number
  net: number
  teams: DivisionTeam[]
}

function buildDivisions(records: RecordsResponse, teams: Team[]): Division[] {
  const seriesByTeam = new Map(records.series.map((series) => [series.team, series]))
  const divisions = new Map<string, Division>()
  for (const team of teams) {
    if (team.defunct || !team.conference || !team.division) continue
    const name = `${team.conference} ${team.division}`
    const division = divisions.get(name) ?? {
      name, conference: team.conference, wins: 0, losses: 0, ties: 0, net: 0, teams: [],
    }
    const series = seriesByTeam.get(team.abbr)
    const wins = series?.wins ?? 0
    const losses = series?.losses ?? 0
    const ties = series?.ties ?? 0
    division.wins += wins
    division.losses += losses
    division.ties += ties
    division.net += wins - losses
    division.teams.push({ abbr: team.abbr, name: team.name, color: team.color, wins, losses, ties, net: wins - losses })
    divisions.set(name, division)
  }
  return [...divisions.values()]
    .map((division) => ({ ...division, teams: division.teams.sort((a, b) => b.net - a.net) }))
    .sort(
      (a, b) =>
        a.conference.localeCompare(b.conference) ||
        DIVISION_ORDER.indexOf(a.name.split(' ')[1]) - DIVISION_ORDER.indexOf(b.name.split(' ')[1]),
    )
}

const signed = (value: number) => (value > 0 ? `+${value}` : String(value))

function DivisionTooltip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null
  const division = payload[0].payload as Division
  return (
    <div className="tooltip">
      <div className="tooltip-title">
        {division.name} &middot; {signed(division.net)}
      </div>
      {division.teams.map((team) => (
        <div key={team.abbr} className="tooltip-row">
          <span className="swatch" style={{ background: team.color }} />
          <span className="tooltip-team">{team.abbr}</span>
          <span className="tooltip-value">{signed(team.net)}</span>
        </div>
      ))}
    </div>
  )
}

interface Props {
  records: RecordsResponse | null
  teams: Team[]
  selected: Set<string>
}

export default function DivisionChart({ records, teams, selected }: Props) {
  const divisions = useMemo(
    () => (records ? buildDivisions(records, teams.filter((team) => selected.has(team.abbr))) : []),
    [records, teams, selected],
  )
  const ranked = useMemo(() => [...divisions].sort((a, b) => b.net - a.net), [divisions])
  const axis = useMemo(() => {
    const values = divisions.map((division) => division.net)
    const lo = Math.min(0, ...values)
    const hi = Math.max(0, ...values)
    // Leave headroom above/below the tallest bars for their value labels.
    const raw = Math.max(1, (hi - lo) * 1.2) / 6
    const magnitude = 10 ** Math.floor(Math.log10(raw))
    const step = [1, 2, 5, 10].map((n) => n * magnitude).find((n) => n >= raw) ?? 10 * magnitude
    const min = lo < 0 ? -Math.ceil((-lo * 1.1) / step) * step : 0
    const max = hi > 0 ? Math.ceil((hi * 1.1) / step) * step : lo === 0 ? step : 0
    const ticks: number[] = []
    for (let value = min; value <= max; value += step) ticks.push(value)
    return { min, max, ticks }
  }, [divisions])

  return (
    <>
      <section className="chart-card">
        <ResponsiveContainer width="100%" height={480}>
          <BarChart data={divisions} margin={{ top: 28, right: 24, bottom: 8, left: 8 }}>
            <CartesianGrid stroke="#23283a" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="name" stroke="#7b839c" tick={{ fontSize: 12 }} interval={0} />
            <YAxis
              stroke="#7b839c"
              width={64}
              domain={[axis.min, axis.max]}
              ticks={axis.ticks}
              interval={0}
              label={{ value: 'Combined wins − losses', angle: -90, position: 'insideLeft', fill: '#7b839c' }}
            />
            <ReferenceLine y={0} stroke="#4a5169" strokeWidth={2} />
            <Tooltip content={<DivisionTooltip />} cursor={{ fill: 'rgba(122, 162, 247, 0.08)' }} />
            <Bar dataKey="net" isAnimationActive={false} radius={[3, 3, 3, 3]}>
              {divisions.map((division) => (
                <Cell
                  key={division.name}
                  fill={CONFERENCE_COLORS[division.conference] ?? '#888888'}
                  fillOpacity={division.net >= 0 ? 0.9 : 0.55}
                />
              ))}
              <LabelList
                dataKey="net"
                position="top"
                formatter={(value: number) => signed(value)}
                fill="#c0c6d4"
                fontSize={12}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </section>

      {ranked.length > 0 && (
        <section className="standings">
          <h2>
            Division net record, {records?.start_season}&ndash;{records?.end_season}
          </h2>
          <table>
            <thead>
              <tr>
                <th>Division</th>
                <th>Teams</th>
                <th>GP</th>
                <th>W</th>
                <th>L</th>
                <th>T</th>
                <th>Net</th>
              </tr>
            </thead>
            <tbody>
              {ranked.map((division) => (
                <tr key={division.name}>
                  <td>
                    <span
                      className="swatch"
                      style={{ background: CONFERENCE_COLORS[division.conference] }}
                    />
                    {division.name}
                  </td>
                  <td>{division.teams.map((team) => `${team.abbr} ${signed(team.net)}`).join(', ')}</td>
                  <td>{division.wins + division.losses + division.ties}</td>
                  <td>{division.wins}</td>
                  <td>{division.losses}</td>
                  <td>{division.ties}</td>
                  <td className={division.net >= 0 ? 'pos' : 'neg'}>{signed(division.net)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  )
}
