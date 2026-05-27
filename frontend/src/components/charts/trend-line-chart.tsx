'use client'

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

export type TrendLine = {
  dataKey: string
  name: string
  color: string
}

type TrendLineChartProps = {
  data: Array<Record<string, string | number | null | undefined>>
  lines: TrendLine[]
  xKey?: string
  height?: number
  yDomain?: [number, number]
  emptyLabel?: string
}

const tooltipStyle = {
  background: 'var(--color-bg-card)',
  border: '1px solid var(--color-border-subtle)',
  borderRadius: 8,
  color: 'var(--color-text-primary)',
  boxShadow: 'var(--shadow-card)',
}

export function TrendLineChart({
  data,
  lines,
  xKey = 'label',
  height = 240,
  yDomain = [0, 100],
  emptyLabel = '暂无趋势数据',
}: TrendLineChartProps) {
  if (!data.length) {
    return (
      <div
        className="flex items-center justify-center text-xs"
        style={{ height, color: 'var(--color-text-secondary)' }}
      >
        {emptyLabel}
      </div>
    )
  }

  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
          <CartesianGrid stroke="var(--color-border-subtle)" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey={xKey}
            tick={{ fill: 'var(--color-text-secondary)', fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: 'var(--color-border-subtle)' }}
          />
          <YAxis
            domain={yDomain}
            tick={{ fill: 'var(--color-text-secondary)', fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={38}
          />
          <Tooltip
            contentStyle={tooltipStyle}
            labelStyle={{ color: 'var(--color-text-primary)' }}
            itemStyle={{ fontSize: 12 }}
          />
          <Legend
            iconType="circle"
            wrapperStyle={{ color: 'var(--color-text-secondary)', fontSize: 12, paddingTop: 8 }}
          />
          {lines.map((line) => (
            <Line
              key={line.dataKey}
              type="monotone"
              dataKey={line.dataKey}
              name={line.name}
              stroke={line.color}
              strokeWidth={2}
              dot={{ r: 3, strokeWidth: 1 }}
              activeDot={{ r: 5 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
