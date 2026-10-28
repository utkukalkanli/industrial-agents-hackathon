// The Floorwise mark: a route climbing a grid of rooms, start dot to end dot (same drawing as public/favicon.svg).
// Drawn in currentColor, so it follows light/dark with the text around it.
export function Logo() {
  return (
    <span className="logo">
      <svg className="logo-mark" viewBox="0 0 24 24" aria-hidden>
        <g className="logo-grid">
          {[5, 12, 19].flatMap((y) => [5, 12, 19].map((x) => <circle key={`${x}-${y}`} cx={x} cy={y} r="1.6" />))}
        </g>
        <path d="M5 19H12V12H19V5" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"
          strokeLinejoin="round" />
        <circle cx="5" cy="19" r="2.6" fill="currentColor" />
        <circle cx="19" cy="5" r="3.4" fill="currentColor" />
      </svg>
      <span className="logo-word">
        Floor<span>wise</span>
      </span>
    </span>
  )
}
