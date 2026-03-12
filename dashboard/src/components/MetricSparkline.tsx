/**
 * MetricSparkline — Recharts real-time sparkline for stroke rate or other metrics.
 */

import {
  ResponsiveContainer,
  LineChart,
  Line,
  YAxis,
} from "recharts";

type MetricSparklineProps = {
  data: number[];
  label: string;
  color?: string;
};

export function MetricSparkline({
  data,
  label,
  color = "hsl(12, 76%, 61%)",
}: MetricSparklineProps) {
  const chartData = data.map((value, index) => ({ index, value }));

  return (
    <div className="rounded-xl bg-card p-4 shadow-sm border border-border">
      <div className="text-xs text-muted-foreground mb-2">{label}</div>
      <div className="h-24">
        {chartData.length > 1 ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <YAxis domain={["dataMin - 2", "dataMax + 2"]} hide />
              <Line
                type="monotone"
                dataKey="value"
                stroke={color}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
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
