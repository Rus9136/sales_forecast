interface SparklineProps {
  data: number[]
  width?: number
  height?: number
  color?: string
  strokeWidth?: number
  className?: string
}

export function Sparkline({
  data,
  width = 80,
  height = 28,
  color = 'var(--accent)',
  strokeWidth = 1.5,
  className,
}: SparklineProps) {
  if (!data || data.length === 0) {
    return <svg width={width} height={height} className={className} aria-hidden />
  }

  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const step = data.length > 1 ? width / (data.length - 1) : 0
  const padY = strokeWidth

  const points = data.map((v, i) => {
    const x = i * step
    const y = height - padY - ((v - min) / range) * (height - padY * 2)
    return [x, y] as const
  })

  const polyline = points.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' ')
  const area =
    `M ${points[0][0].toFixed(2)},${height} ` +
    points.map(([x, y]) => `L ${x.toFixed(2)},${y.toFixed(2)}`).join(' ') +
    ` L ${points[points.length - 1][0].toFixed(2)},${height} Z`

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      aria-hidden
      style={{ display: 'block' }}
    >
      <path d={area} fill={color} fillOpacity={0.12} stroke="none" />
      <polyline
        points={polyline}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}
