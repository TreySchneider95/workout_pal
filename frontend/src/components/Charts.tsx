/**
 * Single-series charts. One series => no legend; the card title names it.
 * Solid hairline grid, 2px lines, >=8px markers, 4px rounded bar ends, hover tooltips.
 */
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export const CHART_COLOR = "#9ccc1f";
const GRID = "#222831";
const AXIS_TEXT = "#8d96a5";

interface Datum {
  label: string;
  value: number | null;
  detail?: string;
}

function ChartTooltip({ active, payload, unit }: { active?: boolean; payload?: { payload: Datum }[]; unit?: string }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded-xl border border-border bg-elevated px-3 py-2 text-sm shadow-xl">
      <div className="text-xs text-muted-foreground">{d.label}</div>
      <div className="tabular font-semibold text-foreground">
        {d.value ?? "–"}
        {unit ? ` ${unit}` : ""}
      </div>
      {d.detail && <div className="text-xs text-muted-foreground">{d.detail}</div>}
    </div>
  );
}

const axisProps = {
  tick: { fill: AXIS_TEXT, fontSize: 12 },
  tickLine: false,
  axisLine: { stroke: GRID },
} as const;

export function LineTrend({ data, unit, height = 220 }: { data: Datum[]; unit?: string; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 12, right: 12, bottom: 0, left: -12 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="label" {...axisProps} minTickGap={24} />
        <YAxis {...axisProps} axisLine={false} width={48} allowDecimals={false} domain={["auto", "auto"]} />
        <Tooltip content={<ChartTooltip unit={unit} />} cursor={{ stroke: AXIS_TEXT, strokeWidth: 1 }} />
        <Line
          type="monotone"
          dataKey="value"
          stroke={CHART_COLOR}
          strokeWidth={2}
          dot={{ r: 4, fill: CHART_COLOR, stroke: "#13161b", strokeWidth: 2 }}
          activeDot={{ r: 6, fill: CHART_COLOR, stroke: "#13161b", strokeWidth: 2 }}
          connectNulls
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function BarTrend({ data, unit, height = 200 }: { data: Datum[]; unit?: string; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 12, right: 12, bottom: 0, left: -12 }} barCategoryGap={2}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="label" {...axisProps} minTickGap={16} />
        <YAxis {...axisProps} axisLine={false} width={48} allowDecimals={false} />
        <Tooltip content={<ChartTooltip unit={unit} />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
        <Bar dataKey="value" fill={CHART_COLOR} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
