import { useState } from 'react'
import QbChart from './QbChart'
import QbTdIntChart from './QbTdIntChart'
import QbTimeline from './QbTimeline'
import type { QbTimelineMetric } from './api'

const VIEWS = [
  { id: 'games', label: 'Games' },
  { id: 'td', label: 'TD' },
  { id: 'int', label: 'INT' },
  { id: 'tdint', label: 'TD/INT' },
] as const

type ViewId = (typeof VIEWS)[number]['id']
type Resolution = 'game' | 'season'

export default function Quarterbacks() {
  const [view, setView] = useState<ViewId>('games')
  const [resolution, setResolution] = useState<Resolution>('game')
  const metric: QbTimelineMetric = view === 'games' ? 'games' : view === 'tdint' ? 'td_int' : view

  return (
    <>
      <nav className="tabs sub" role="tablist">
        {VIEWS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            role="tab"
            aria-selected={view === entry.id}
            className={`tab${view === entry.id ? ' active' : ''}`}
            onClick={() => setView(entry.id)}
          >
            {entry.label}
          </button>
        ))}
      </nav>

      <nav className="tabs sub resolution-tabs" role="tablist" aria-label="Time resolution">
        <button
          type="button"
          role="tab"
          aria-selected={resolution === 'game'}
          className={`tab${resolution === 'game' ? ' active' : ''}`}
          onClick={() => setResolution('game')}
        >
          Game-by-game
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={resolution === 'season'}
          className={`tab${resolution === 'season' ? ' active' : ''}`}
          onClick={() => setResolution('season')}
        >
          Season timeline
        </button>
      </nav>

      {resolution === 'season' ? (
        <QbTimeline metric={metric} />
      ) : view === 'games' ? (
        <QbChart />
      ) : (
        <QbTdIntChart metric={metric === 'games' ? 'td_int' : metric} />
      )}
    </>
  )
}
