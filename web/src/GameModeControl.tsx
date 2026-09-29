import type { GameMode, TeamGameMode } from './api'

const MODES: { id: GameMode; label: string }[] = [
  { id: 'all', label: 'All games' },
  { id: 'regular', label: 'Regular Season' },
  { id: 'playoffs', label: 'Playoffs' },
]

interface Props<T extends GameMode | TeamGameMode> {
  value: T
  onChange: (mode: T) => void
  includeSuperBowls?: boolean
}

export default function GameModeControl<T extends GameMode | TeamGameMode>({
  value,
  onChange,
  includeSuperBowls = false,
}: Props<T>) {
  const modes = includeSuperBowls
    ? [...MODES, { id: 'superbowls' as GameMode, label: 'Super Bowls' }]
    : MODES
  return (
    <div className="mode-control" role="group" aria-label="Game type">
      {modes.map((mode) => (
        <button
          key={mode.id}
          type="button"
          className={`mode-option${value === mode.id ? ' selected' : ''}`}
          aria-pressed={value === mode.id}
          onClick={() => onChange(mode.id as T)}
        >
          {mode.label}
        </button>
      ))}
    </div>
  )
}