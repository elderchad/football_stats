import type { NcaafGameMode } from './api'

const MODES: { id: NcaafGameMode; label: string }[] = [
  { id: 'all', label: 'All Games' },
  { id: 'regular', label: 'Regular Season' },
  { id: 'bowl', label: 'Bowl Games' },
  { id: 'head_to_head', label: 'Head to Head' },
]

interface Props {
  value: NcaafGameMode
  onChange: (mode: NcaafGameMode) => void
}

export default function NcaafModeControl({ value, onChange }: Props) {
  return (
    <div className="mode-control" role="group" aria-label="College game type">
      {MODES.map((mode) => (
        <button
          key={mode.id}
          type="button"
          className={`mode-option${value === mode.id ? ' selected' : ''}`}
          aria-pressed={value === mode.id}
          onClick={() => onChange(mode.id)}
        >
          {mode.label}
        </button>
      ))}
    </div>
  )
}
