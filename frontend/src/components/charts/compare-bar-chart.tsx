'use client'

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

export type CompareBar = {
  dataKey: string
  name: string
  color: string
}

type CompareBarChartProps = {
  data: Array<Record<string, string | number | null | undefined>>
  bars: CompareBar[]
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

export function CompareBarChart({
  data,
  bars,
  xKey = 'label',
  height = 240,
  yDomain = [0, 100],
  emptyLabel = '暂无对比数据',
}: CompareBarChartProps) {
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
        <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
          <CartesianGrid stroke="var(--color-border-subtle)" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey={xKey}
            tick={{ fill: 'var(--color-text-secondary)', fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: 'var(--color-border-subtle)' }}
            interval={0}
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
            cursor={{ fill: 'rgba(148, 163, 184, 0.08)' }}
          />
          <Legend
            iconType="circle"
            wrapperStyle={{ color: 'var(--color-text-secondary)', fontSize: 12, paddingTop: 8 }}
          />
          {bars.map((bar) => (
            <Bar
              key={bar.dataKey}
              dataKey={bar.dataKey}
              name={bar.name}
              fill={bar.color}
              radius={[5, 5, 0, 0]}
              maxBarSize={42}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
