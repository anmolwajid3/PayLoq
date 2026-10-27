import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Lang } from "../i18n";
import { t } from "../i18n";
import { fmtEur } from "../lib/format";

const tooltipStyle = {
  background: "#123f3c",
  border: "1px solid rgba(232,242,239,0.12)",
  borderRadius: 4,
  color: "#e8f2ef",
};

export function BalanceHistoryChart({
  data,
  lang = "fi",
}: {
  data: { date: string; balance: number }[];
  lang?: Lang;
}) {
  return (
    <div className="chart-wrap">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <defs>
            <linearGradient id="cashFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#d4a017" stopOpacity={0.45} />
              <stop offset="100%" stopColor="#d4a017" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(232,242,239,0.08)" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: "#a7c4bf", fontSize: 12 }} minTickGap={28} />
          <YAxis tick={{ fill: "#a7c4bf", fontSize: 12 }} tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
          <Tooltip contentStyle={tooltipStyle} formatter={(v) => fmtEur(Number(v), lang)} />
          <Area
            type="monotone"
            dataKey="balance"
            stroke="#d4a017"
            fill="url(#cashFill)"
            strokeWidth={2}
            name={t("cash", lang)}
            animationDuration={900}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ProjectionChart({
  data,
  lang = "fi",
}: {
  data: {
    week: number;
    week_end: string;
    projected_balance: number;
    sales_inflow: number;
    purchase_outflow: number;
  }[];
  lang?: Lang;
}) {
  const rows = data.map((d) => ({
    ...d,
    label: `W${d.week}`,
  }));
  return (
    <div className="chart-wrap">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows}>
          <CartesianGrid stroke="rgba(232,242,239,0.08)" vertical={false} />
          <XAxis dataKey="label" tick={{ fill: "#a7c4bf", fontSize: 12 }} />
          <YAxis tick={{ fill: "#a7c4bf", fontSize: 12 }} tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
          <Tooltip contentStyle={tooltipStyle} formatter={(v) => fmtEur(Number(v), lang)} />
          <Legend />
          <Line
            type="monotone"
            dataKey="projected_balance"
            stroke="#3dbf8f"
            strokeWidth={2.5}
            dot={{ r: 3 }}
            name={t("projectedBalance", lang)}
            animationDuration={900}
          />
          <Line
            type="monotone"
            dataKey="sales_inflow"
            stroke="#f0d78a"
            strokeWidth={1.5}
            strokeDasharray="4 4"
            name={t("salesInflow", lang)}
            animationDuration={1100}
          />
          <Line
            type="monotone"
            dataKey="purchase_outflow"
            stroke="#e07060"
            strokeWidth={1.5}
            strokeDasharray="4 4"
            name={t("purchaseOutflow", lang)}
            animationDuration={1100}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
