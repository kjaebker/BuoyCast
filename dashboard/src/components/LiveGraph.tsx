/**
 * LiveGraph — the last ~5 minutes of one metric, shown in place of the
 * rowing scene. Gaps where the rower was resting stay gaps.
 */

import { Area, AreaChart, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { formatNum, formatPace } from "@/lib/format";
import type { MetricSample } from "@/hooks/useWorkoutSocket";

export const GraphMetric = {
  PACE: "pace",
  POWER: "power",
  STROKE_RATE: "strokeRate",
  HEART_RATE: "heartRate",
} as const;
export type GraphMetric = (typeof GraphMetric)[keyof typeof GraphMetric];

type MetricSpec = {
  label: string;
  unit: string;
  color: string;
  format: (v: number | null) => string;
  /** Lower is better (pace): flip the axis so "up" always means harder. */
  reversed?: boolean;
  /** Padding added above and below the data range. */
  pad: number;
};

const SPECS: Record<GraphMetric, MetricSpec> = {
  pace: { label: "Pace", unit: "/500m", color: "var(--color-chart-1)", format: formatPace, reversed: true, pad: 5 },
  power: { label: "Power", unit: "W", color: "var(--color-chart-5)", format: (v) => formatNum(v), pad: 10 },
  strokeRate: { label: "Stroke rate", unit: "spm", color: "var(--color-chart-2)", format: (v) => formatNum(v, 0), pad: 2 },
  heartRate: { label: "Heart rate", unit: "bpm", color: "var(--color-chart-4)", format: (v) => formatNum(v), pad: 5 },
};

const EMPTY_TEXT: Record<GraphMetric, string> = {
  pace: "Start rowing to see your pace",
  power: "Start rowing to see your power",
  strokeRate: "Start rowing to see your stroke rate",
  heartRate: "No heart rate yet. Is the strap connected?",
};

type LiveGraphProps = {
  metric: GraphMetric;
  samples: MetricSample[];
  /** The live value shown in the header (may differ from the last sample, e.g. decayed stroke rate). */
  current: number | null;
};

export function LiveGraph({ metric, samples, current }: LiveGraphProps) {
  const spec = SPECS[metric];
  const data = samples.map((s) => ({ at: s.at, value: s[metric] }));
  const values = data.flatMap((d) => (d.value == null ? [] : [d.value]));
  const hasData = values.length > 1;
  const avg = values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
  const gradientId = `live-graph-${metric}`;

  return (
    <div className="relative mb-3 h-[200px] overflow-hidden rounded-2xl border border-border/80 bg-[#0a1428] md:h-[240px] [@media(min-width:768px)_and_(max-height:820px)]:h-[160px]">
      <div className="pointer-events-none absolute inset-x-4 top-3 z-10 flex items-start justify-between">
        <div>
          <div
            className="text-[0.7rem] font-semibold uppercase tracking-[0.18em]"
            style={{ color: spec.color }}
          >
            {spec.label}
          </div>
          <div className="flex items-end gap-1.5">
            <span className="text-4xl font-bold tabular-nums text-foreground">
              {spec.format(current)}
            </span>
            <span className="pb-1 text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
              {spec.unit}
            </span>
          </div>
        </div>
        {avg != null && (
          <div className="text-right">
            <div className="text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              5 min avg
            </div>
            <div className="text-lg font-semibold tabular-nums text-foreground/85">
              {spec.format(avg)}
            </div>
          </div>
        )}
      </div>

      {hasData ? (
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 72, right: 0, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={spec.color} stopOpacity={0.45} />
                <stop offset="100%" stopColor={spec.color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="at" type="number" domain={["dataMin", "dataMax"]} hide />
            <YAxis
              hide
              reversed={spec.reversed}
              domain={[`dataMin - ${spec.pad}`, `dataMax + ${spec.pad}`]}
            />
            {avg != null && (
              <ReferenceLine
                y={avg}
                stroke="currentColor"
                className="text-muted-foreground"
                strokeOpacity={0.5}
                strokeDasharray="4 4"
              />
            )}
            <Area
              type="monotone"
              dataKey="value"
              stroke={spec.color}
              strokeWidth={2.5}
              fill={`url(#${gradientId})`}
              // Pace is reversed, so fill toward the bottom of the reversed axis.
              baseValue={spec.reversed ? "dataMax" : "dataMin"}
              isAnimationActive={false}
              connectNulls={false}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      ) : (
        <div className="flex h-full items-end justify-center pb-8 text-sm text-muted-foreground">
          {EMPTY_TEXT[metric]}
        </div>
      )}
    </div>
  );
}
