import { useState } from 'react'
import DataAudit from './DataAudit'
import NcaafChart from './NcaafChart'
import Quarterbacks from './Quarterbacks'
import TeamChart from './TeamChart'

const NFL_TABS = [
  { id: 'teams', label: 'Franchises' },
  { id: 'quarterbacks', label: 'Quarterbacks' },
] as const

type LeagueId = 'nfl' | 'ncaaf' | 'audit'
type NflTabId = (typeof NFL_TABS)[number]['id']

const LEAGUE_LABELS: Record<LeagueId, string> = { nfl: 'NFL', ncaaf: 'NCAAF', audit: 'Data audit' }

export default function App() {
  const [league, setLeague] = useState<LeagueId>('nfl')
  const [nflTab, setNflTab] = useState<NflTabId>('teams')

  return (
    <div className="app">
      <header>
        <h1>Football Record Walk</h1>
        <nav className="tabs league-tabs" role="tablist" aria-label="League">
          {(['nfl', 'ncaaf', 'audit'] as const).map((entry) => (
            <button
              key={entry}
              type="button"
              role="tab"
              aria-selected={league === entry}
              className={`tab${league === entry ? ' active' : ''}`}
              onClick={() => setLeague(entry)}
            >
              {LEAGUE_LABELS[entry]}
            </button>
          ))}
        </nav>
      </header>

      {league === 'nfl' ? (
        <>
          <nav className="tabs sub section-tabs" role="tablist" aria-label="NFL view">
            {NFL_TABS.map((entry) => (
              <button
                key={entry.id}
                type="button"
                role="tab"
                aria-selected={nflTab === entry.id}
                className={`tab${nflTab === entry.id ? ' active' : ''}`}
                onClick={() => setNflTab(entry.id)}
              >
                {entry.label}
              </button>
            ))}
          </nav>
          {nflTab === 'teams' ? <TeamChart /> : <Quarterbacks />}
        </>
      ) : league === 'ncaaf' ? (
        <NcaafChart />
      ) : (
        <DataAudit />
      )}

      <footer>
        Data:{' '}
        {league === 'nfl' ? (
          <a href="https://github.com/nflverse/nfldata">nflverse/nfldata</a>
        ) : league === 'audit' ? (
          <>
            <a href="https://github.com/nflverse/nfldata">nflverse</a>
            {' · '}
            <a href="https://github.com/fivethirtyeight/data/tree/master/nfl-elo">FiveThirtyEight NFL Elo</a>
            {' · '}
            <a href="https://github.com/sportsdataverse/cfbfastR-data">cfbfastR-data</a>
            {' · '}
            published season and rivalry histories
          </>
        ) : (
          <>
            <a href="https://github.com/sportsdataverse/cfbfastR-data">cfbfastR-data</a>
            {' · '}
            <a href="https://en.wikipedia.org/wiki/List_of_Utah_Utes_football_seasons">published season/bowl histories</a>
          </>
        )}
      </footer>
    </div>
  )
}
