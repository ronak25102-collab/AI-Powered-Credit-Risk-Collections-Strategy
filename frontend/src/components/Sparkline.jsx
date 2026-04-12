/**
 * Tiny inline SVG sparkline chart.
 * @param {{ data: number[], width?: number, height?: number, color?: string }} props
 */
export default function Sparkline({
  data = [],
  width = 80,
  height = 28,
  color = "#ff9466",
}) {
  if (!data.length || data.length < 2) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const padding = 2;

  const points = data
    .map((value, i) => {
      const x = padding + (i / (data.length - 1)) * (width - padding * 2);
      const y = height - padding - ((value - min) / range) * (height - padding * 2);
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg
      className="sparkline"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
    >
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Dot at the last data point */}
      {(() => {
        const lastX = padding + ((data.length - 1) / (data.length - 1)) * (width - padding * 2);
        const lastY = height - padding - ((data[data.length - 1] - min) / range) * (height - padding * 2);
        return <circle cx={lastX} cy={lastY} r="2" fill={color} />;
      })()}
    </svg>
  );
}
