import { useEffect, useRef, useState } from 'react'

function readSelection(key: string): Set<string> | null {
  try {
    const raw = sessionStorage.getItem(key)
    if (raw === null) return null
    const values: unknown = JSON.parse(raw)
    return Array.isArray(values) && values.every((value) => typeof value === 'string')
      ? new Set(values)
      : null
  } catch {
    return null
  }
}

export default function useSelection(key: string) {
  const [saved] = useState(() => readSelection(key))
  const initialized = useRef(saved !== null)
  const [state, updateState] = useState({ key, selected: saved ?? new Set<string>() })
  const selected = state.selected

  useEffect(() => {
    if (state.key === key) return
    const selection = readSelection(key)
    initialized.current = selection !== null
    updateState({ key, selected: selection ?? new Set() })
  }, [key, state.key])

  useEffect(() => {
    if (!initialized.current || state.key !== key) return
    try {
      sessionStorage.setItem(key, JSON.stringify([...selected]))
    } catch {
      return
    }
  }, [key, selected, state.key])

  const setSelected: React.Dispatch<React.SetStateAction<Set<string>>> = (selection) => {
    initialized.current = true
    updateState((previous) => ({
      key,
      selected: typeof selection === 'function' ? selection(previous.selected) : selection,
    }))
  }

  const initializeSelection = (defaults: Set<string>) => {
    if (initialized.current) return
    initialized.current = true
    updateState({ key, selected: defaults })
  }

  return { selected, setSelected, initializeSelection }
}