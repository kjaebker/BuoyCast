/**
 * MetricSparkline — dual-axis Recharts sparkline for stroke rate and heart rate.
 *
 * Stroke rate is plotted on the left Y-axis, heart rate on the right.
 * When HR data is available, the current HR value is shown as a label
 * with a pulsing heart icon.
 */

import {
  ResponsiveContainer,
  LineChart,
  Line,
  YAxis,
} from "recharts";
import { Heart } from "lucide-react";

type SparklinePoint = {
  index: number;
  strokeRate: number | null;
  heartRate: number | null;
};

type MetricSparklineProps = {
  strokeRateData: number[];
  heartRateData: number[];
  currentHr: number | null;
  hrConnected: boolean;
  label: string;
  strokeRateColor?: string;
  heartRateColor?: string;
};

export function MetricSparkline({
  strokeRateData,
  heartRateData,
  currentHr,
  hrConnected,
  label,
  strokeRateColor = "var(--color-chart-2)",
  heartRateColor = "var(--color-chart-4)",
}: MetricSparklineProps) {
  // Build unified dataset — align from the right (most recent) so both
  // series share a time axis even if they have different lengths.
  const maxLen = Math.max(strokeRateData.length, heartRateData.length);
  const chartData: SparklinePoint[] = [];
  for (let i = 0; i < maxLen; i++) {
    const srIdx = i - (maxLen - strokeRateData.length);
    const hrIdx = i - (maxLen - heartRateData.length);
    chartData.push({
      index: i,
      strokeRate: srIdx >= 0 ? strokeRateData[srIdx] : null,
      heartRate: hrIdx >= 0 ? heartRateData[hrIdx] : null,
    });
  }

  const hasData = chartData.length > 1;

  return (
    <div className="rounded-xl bg-card p-4 shadow-sm border border-border">
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs text-muted-foreground">{label}</div>
        {hrConnected && currentHr != null && (
          <div className="flex items-center gap-1.5 text-[var(--color-chart-4)]">
            <span
              style={{
                display: "inline-flex",
                animation: `heartbeat ${(60 / currentHr).toFixed(2)}s ease-in-out infinite`,
                transformOrigin: "center",
              }}
            >
              <Heart className="h-3.5 w-3.5 fill-current" />
            </span>
            <span className="text-sm font-bold tabular-nums">{currentHr}</span>
            <span className="text-[0.65rem] font-medium uppercase tracking-wider opacity-70">
              bpm
            </span>
          </div>
        )}
      </div>
      <div className="h-24">
        {hasData ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <YAxis
                yAxisId="sr"
                domain={["dataMin - 2", "dataMax + 2"]}
                hide
              />
              {hrConnected && (
                <YAxis
                  yAxisId="hr"
                  orientation="right"
                  domain={["dataMin - 5", "dataMax + 5"]}
                  hide
                />
              )}
              <Line
                yAxisId="sr"
                type="monotone"
                dataKey="strokeRate"
                stroke={strokeRateColor}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
              {hrConnected && (
                <Line
                  yAxisId="hr"
                  type="monotone"
                  dataKey="heartRate"
                  stroke={heartRateColor}
                  strokeWidth={1.5}
                  strokeDasharray="4 2"
                  dot={false}
                  isAnimationActive={false}
                  connectNulls
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
            Waiting for data...
          </div>
        )}
      </div>
    </div>
  );
}
