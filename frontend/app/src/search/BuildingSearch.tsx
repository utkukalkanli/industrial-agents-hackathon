// List view: one search field over every building in the catalogue (GET /buildings), the ones without a real
// position (not on the map) included. Type to filter (name, id, type; accents ignored, every word must match),
// narrow by type or to the buildings with no location, ↑/↓ + Enter or click to open the twin.

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useAccess } from '../access/auth'
import { api, type Building } from '../api'
import { Logo } from '../ui/Logo.tsx'
import './search.css'

const KINDS = [
  { key: 'osm', label: 'OpenStreetMap', test: (id: string) => id.includes('/osm-way') },
  { key: 'campus', label: 'Campus', test: (id: string) => id.includes('/proc-campus') },
  { key: 'factory', label: 'Factory', test: (id: string) => id.includes('/proc-factory') },
  { key: 'residence', label: 'Residence', test: (id: string) => id.includes('/resplan-') },
  { key: 'swiss', label: 'Swiss dwelling', test: (id: string) => id.includes('/swiss-') },
] as const
type KindKey = (typeof KINDS)[number]['key']

const kindOf = (id: string) => KINDS.find((k) => k.test(id))
const NO_LOCATION = 'nolocation'
const fold = (text: string) => text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

type Row = Building & { kind: string; kindKey: KindKey | null; haystack: string }
type Filter = KindKey | typeof NO_LOCATION

export function BuildingSearch({ onOpen, onMap, onImport }: { onOpen: (id: string) => void; onMap: () => void; onImport: () => void }) {
  const [buildings, setBuildings] = useState<Row[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState<Filter | null>(null)
  const [active, setActive] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  const list = useRef<HTMLOListElement>(null)
  const { version, mode, admin } = useAccess() // access mode: the list depends on who is signed in

  useEffect(() => {
    api.buildings()
      .then((items) =>
        setBuildings(
          items
            .map((b) => {
              const k = kindOf(b.id)
              const name = b.name ?? b.id.split('/')[1]
              return { ...b, name, kind: k?.label ?? 'Building', kindKey: k?.key ?? null, haystack: fold(`${name} ${b.id} ${k?.label ?? ''}`) }
            })
            .sort((a, b) => a.name!.localeCompare(b.name!, undefined, { numeric: true })),
        ),
      )
      .catch((reason) => setError(String(reason)))
  }, [version])

  const counts = useMemo(() => {
    const c = new Map<Filter, number>()
    for (const b of buildings ?? []) {
      if (b.kindKey) c.set(b.kindKey, (c.get(b.kindKey) ?? 0) + 1)
      if (!b.location) c.set(NO_LOCATION, (c.get(NO_LOCATION) ?? 0) + 1)
    }
    return c
  }, [buildings])

  const results = useMemo(() => {
    const words = fold(query).split(/\s+/).filter(Boolean)
    const matches = (b: Row) => !kind || (kind === NO_LOCATION ? !b.location : b.kindKey === kind)
    return (buildings ?? []).filter((b) => matches(b) && words.every((w) => b.haystack.includes(w)))
  }, [buildings, query, kind])

  useEffect(() => {
    list.current?.children[active]?.scrollIntoView({ block: 'nearest' })
  }, [active])
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === '/' && document.activeElement !== input.current) { e.preventDefault(); input.current?.focus() }
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [])

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => Math.min(results.length - 1, i + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(0, i - 1)) }
    else if (e.key === 'Enter' && results[active]) onOpen(results[active].id)
    else if (e.key === 'Escape') { setQuery(''); setActive(0) }
  }

  return (
    <main className="bs">
      <div className="bs-inner">
        <div className="bs-top">
          <button className="bs-map" onClick={onMap}>← Map</button>
          {(!mode || admin) && <button className="bs-map" onClick={onImport}>New from floor plans →</button>}
        </div>
        <header className="bs-head">
          <Logo />
          <h1>Find a building</h1>
          <p>{buildings ? `${buildings.length} buildings` : error ? 'Could not load buildings' : 'Loading…'}</p>
        </header>

        <label className="bs-field">
          <svg viewBox="0 0 24 24" aria-hidden><circle cx="11" cy="11" r="6.5" /><path d="M16 16l4.5 4.5" /></svg>
          <input
            ref={input}
            autoFocus
            value={query}
            onChange={(e) => { setQuery(e.target.value); setActive(0) }}
            onKeyDown={onKeyDown}
            placeholder="Search by name or id"
            aria-label="Search buildings"
            aria-controls="bs-results"
            aria-activedescendant={results[active] ? `bs-${results[active].id}` : undefined}
            spellCheck={false}
          />
          {query && <button className="bs-clear" onClick={() => { setQuery(''); setActive(0); input.current?.focus() }} aria-label="Clear search">×</button>}
        </label>

        <div className="bs-kinds" role="group" aria-label="Filter by type">
          <button className={kind === null ? 'on' : ''} onClick={() => { setKind(null); setActive(0) }}>All</button>
          {KINDS.map((k) => (
            <button key={k.key} className={kind === k.key ? 'on' : ''} onClick={() => { setKind(kind === k.key ? null : k.key); setActive(0) }}>
              {k.label}<span>{counts.get(k.key) ?? 0}</span>
            </button>
          ))}
          <button className={kind === NO_LOCATION ? 'on' : ''} onClick={() => { setKind(kind === NO_LOCATION ? null : NO_LOCATION); setActive(0) }}>
            No location<span>{counts.get(NO_LOCATION) ?? 0}</span>
          </button>
        </div>

        {error && <p className="bs-empty">{error}</p>}
        {buildings && (
          <>
            <p className="bs-count" aria-live="polite">{results.length === buildings.length ? 'All buildings' : `${results.length} of ${buildings.length}`}</p>
            <ol className="bs-results" id="bs-results" ref={list} role="listbox">
              {results.map((b, i) => (
                <li key={b.id} id={`bs-${b.id}`} role="option" aria-selected={i === active}>
                  <button className={i === active ? 'on' : ''} onMouseEnter={() => setActive(i)} onClick={() => onOpen(b.id)}>
                    <span className="bs-name">{b.name}</span>
                    <span className="bs-kind">{b.location ? `${b.kind} · on map` : b.kind}</span>
                    <span className="bs-id">{b.id}</span>
                  </button>
                </li>
              ))}
            </ol>
            {!results.length && <p className="bs-empty">No building matches “{query}”.</p>}
          </>
        )}
      </div>
    </main>
  )
}
