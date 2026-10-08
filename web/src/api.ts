export interface Team {
  abbr: string
  name: string
  conference: string
  division: string
  color: string
  alt_color: string
  defunct: boolean
  first_season: number
  last_season: number
  games: number
}

export type GameMode = 'all' | 'regular' | 'playoffs' | 'superbowls'
export type TeamGameMode = GameMode
export type NcaafGameMode = 'all' | 'regular' | 'bowl' | 'head_to_head'

export interface Step {
  season: number
  week: number
  label: string
}

export type EventKind =
  | 'title'
  | 'mvp'
  | 'runnerup'
  | 'conference'
  | 'arrival'
  | 'departure'
  | 'move'
  | 'season'
  | 'milestone'

/** A notable event placed on a step of a team walk. */
export interface StepEvent {
  step: number
  series: string
  kind: EventKind
  label: string
  priority: number
}

/** A notable event on one quarterback's line, at x (step or season). */
export interface SeriesEvent {
  x: number
  kind: EventKind
  label: string
  priority: number
}

export interface Series {
  team: string
  values: (number | null)[]
  /** Step index of each game the team played, with its result (+1 win, -1 loss, 0 tie). */
  game_steps?: number[]
  game_results?: number[]
  wins: number
  losses: number
  ties: number
  final: number | null
}

export interface RecordsResponse {
  steps: Step[]
  events: StepEvent[]
  series: Series[]
  start_season: number
  end_season: number
  game_mode: TeamGameMode
}

export interface SeasonsResponse {
  min: number
  max: number
  seasons: number[]
}

export interface NcaafTeam {
  abbr: string
  name: string
  color: string
}

export interface NcaafRivalry {
  id: string
  name: string
  nickname: string
}

export interface NcaafRecordsResponse {
  steps: Step[]
  events: StepEvent[]
  series: Series[]
  start_season: number
  end_season: number
  game_mode: NcaafGameMode
}

export interface QbStint {
  team: string
  start: number
  end: number
}

export interface Quarterback {
  id: string
  name: string
  status: 'hof' | 'likely'
  entered: number
  first_season: number
  last_season: number
  truncated: boolean
  teams: QbStint[]
  color: string
}

export interface QbSeries {
  id: string
  name: string
  status: 'hof' | 'likely'
  color: string
  values: number[]
  labels: string[]
  seasons: number[]
  wins: number
  losses: number
  ties: number
  final: number
  events: SeriesEvent[]
}

export interface QbRecordsResponse {
  series: QbSeries[]
  max_steps: number
  game_mode: GameMode
}

export interface QbTdIntSeries {
  id: string
  name: string
  status: 'hof' | 'likely'
  color: string
  values: number[]
  labels: string[]
  touchdowns: number
  interceptions: number
  games: number
  first_season: number
  final: number
  events: SeriesEvent[]
}

export interface QbTdIntResponse {
  series: QbTdIntSeries[]
  max_steps: number
  game_mode: GameMode
  stats_start_season: number
}

export type QbTimelineMetric = 'games' | 'td' | 'int' | 'td_int'

export interface QbTimelineSeries {
  id: string
  name: string
  status: 'hof' | 'likely'
  color: string
  values: (number | null)[]
  games: number
  touchdowns: number
  interceptions: number
  final: number | null
  first_season: number | null
  events: SeriesEvent[]
}

export interface QbTimelineResponse {
  seasons: number[]
  series: QbTimelineSeries[]
  metric: QbTimelineMetric
  game_mode: GameMode
  stats_start_season: number
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`${path} failed: ${response.status} ${response.statusText}`)
  }
  return (await response.json()) as T
}

export const fetchTeams = () => getJson<Team[]>('/api/teams')

export type AuditStatus = 'pass' | 'warn' | 'fail' | 'error'

export interface AuditCheck {
  id: string
  title: string
  scope: string
  status: AuditStatus
  checked: number
  issue_count: number
  issues: string[]
  note: string
}

export interface AuditReport {
  generated_at: string
  summary: Record<AuditStatus, number>
  checks: AuditCheck[]
  limitations: string[]
}

export const fetchAudit = (refresh = false) =>
  getJson<AuditReport>(`/api/audit${refresh ? '?refresh=true' : ''}`)

export const fetchSeasons = () => getJson<SeasonsResponse>('/api/seasons')

export const fetchNcaafRivalries = () =>
  getJson<NcaafRivalry[]>('/api/ncaaf/rivalries')

export const fetchNcaafTeams = (rivalry: string) =>
  getJson<NcaafTeam[]>(`/api/ncaaf/teams?rivalry=${encodeURIComponent(rivalry)}`)

export const fetchNcaafSeasons = (rivalry: string) =>
  getJson<SeasonsResponse>(`/api/ncaaf/seasons?rivalry=${encodeURIComponent(rivalry)}`)

export interface NcaafRankingSeries {
  team: string
  /** 25 for #1 down to 1 for #25; 0 when unranked. */
  values: number[]
  polls: number
  ranked: number
  best: number | null
  weeks_at_1: number
  final: number
}

export interface NcaafRankingsResponse {
  steps: Step[]
  series: NcaafRankingSeries[]
  start_season: number
  end_season: number
  rivalry_id: string
  poll: string
  poll_size: number
  missing_seasons: number[]
  first_poll_season: number
}

export const fetchNcaafRankings = (rivalry: string, start?: number, end?: number) =>
  getJson<NcaafRankingsResponse>(
    `/api/ncaaf/rankings?rivalry=${encodeURIComponent(rivalry)}` +
      (start ? `&start_season=${start}` : '') +
      (end ? `&end_season=${end}` : ''),
  )

export function fetchNcaafRecords(
  startSeason: number,
  endSeason: number,
  gameMode: NcaafGameMode,
  rivalry: string,
): Promise<NcaafRecordsResponse> {
  const params = new URLSearchParams({
    start_season: String(startSeason),
    end_season: String(endSeason),
    game_mode: gameMode,
    rivalry,
  })
  return getJson<NcaafRecordsResponse>(`/api/ncaaf/records?${params.toString()}`)
}

export function fetchRecords(
  startSeason: number,
  endSeason: number,
  gameMode: TeamGameMode,
): Promise<RecordsResponse> {
  const params = new URLSearchParams({
    start_season: String(startSeason),
    end_season: String(endSeason),
    game_mode: gameMode,
  })
  return getJson<RecordsResponse>(`/api/records?${params.toString()}`)
}

export const fetchQuarterbacks = () => getJson<Quarterback[]>('/api/quarterbacks')

export function fetchQbRecords(
  ids: string[],
  gameMode: GameMode,
): Promise<QbRecordsResponse> {
  const params = new URLSearchParams({
    ids: ids.join(','),
    game_mode: gameMode,
  })
  return getJson<QbRecordsResponse>(`/api/qb-records?${params.toString()}`)
}

export function fetchQbTdInt(
  ids: string[],
  gameMode: GameMode,
  metric: 'td' | 'int' | 'td_int' = 'td_int',
): Promise<QbTdIntResponse> {
  const params = new URLSearchParams({
    ids: ids.join(','),
    game_mode: gameMode,
    metric,
  })
  return getJson<QbTdIntResponse>(`/api/qb-td-int?${params.toString()}`)
}

export function fetchQbTimeline(
  ids: string[],
  gameMode: GameMode,
  metric: QbTimelineMetric,
): Promise<QbTimelineResponse> {
  const params = new URLSearchParams({
    ids: ids.join(','),
    game_mode: gameMode,
    metric,
  })
  return getJson<QbTimelineResponse>(`/api/qb-timeline?${params.toString()}`)
}
