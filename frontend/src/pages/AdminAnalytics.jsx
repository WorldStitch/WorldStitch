import { useQuery } from "@tanstack/react-query";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { analytics } from "@/api";
import SectionHeader from "@/components/SectionHeader";
import Card from "@/components/Card";

function StatCard({ label, value, sub }) {
  return (
    <Card className="p-5 flex flex-col gap-1">
      <p className="text-xs text-txt-muted uppercase tracking-widest font-bold">{label}</p>
      <p className="text-3xl font-bold text-txt">{value}</p>
      {sub && <p className="text-xs text-txt-muted">{sub}</p>}
    </Card>
  );
}

export default function AdminAnalytics() {
  const { data: summary, isLoading: loadingSummary } = useQuery({
    queryKey: ["admin-analytics-summary"],
    queryFn: analytics.summary,
    staleTime: 60_000,
  });

  const { data: byDay = [] } = useQuery({
    queryKey: ["admin-analytics-by-day"],
    queryFn: analytics.eventsByDay,
    staleTime: 60_000,
  });

  const { data: breakdown = [] } = useQuery({
    queryKey: ["admin-analytics-breakdown"],
    queryFn: analytics.breakdown,
    staleTime: 60_000,
  });

  const { data: errors = [] } = useQuery({
    queryKey: ["admin-analytics-errors"],
    queryFn: analytics.errors,
    staleTime: 60_000,
  });

  const { data: userStats = [] } = useQuery({
    queryKey: ["admin-analytics-users"],
    queryFn: analytics.users,
    staleTime: 60_000,
  });

  return (
    <div className="p-8 space-y-8 min-h-full">
      <SectionHeader
        title="Analytics Dashboard"
        subtitle="Last 30 days of usage data (consenting users only)"
      />

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Events"
          value={loadingSummary ? "…" : (summary?.total_events ?? 0).toLocaleString()}
        />
        <StatCard
          label="Active Users"
          value={loadingSummary ? "…" : (summary?.active_users ?? 0).toLocaleString()}
        />
        <StatCard
          label="AI Requests"
          value={loadingSummary ? "…" : (summary?.ai_requests ?? 0).toLocaleString()}
        />
        <StatCard
          label="Est. AI Cost"
          value={
            loadingSummary
              ? "…"
              : `$${(summary?.total_ai_cost_usd ?? 0).toFixed(4)}`
          }
          sub="USD, last 30 days"
        />
      </div>

      {/* Daily event volume */}
      <Card className="p-5">
        <h2 className="text-sm font-semibold text-txt mb-4">Daily Event Volume</h2>
        {byDay.length === 0 ? (
          <p className="text-txt-muted text-sm">No data yet.</p>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={byDay}>
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: "var(--color-txt-muted)" }}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "var(--color-txt-muted)" }}
                tickLine={false}
                axisLine={false}
                width={40}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--color-surface)",
                  border: "1px solid var(--color-border-subtle)",
                  borderRadius: "8px",
                  fontSize: "12px",
                }}
              />
              <Line
                type="monotone"
                dataKey="count"
                stroke="var(--color-accent)"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Card>

      {/* Event breakdown */}
      <Card className="p-5">
        <h2 className="text-sm font-semibold text-txt mb-4">Event Breakdown</h2>
        {breakdown.length === 0 ? (
          <p className="text-txt-muted text-sm">No events recorded yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-txt-muted border-b border-border-subtle">
                <th className="pb-2 font-medium">Event Type</th>
                <th className="pb-2 font-medium text-right">Count</th>
                <th className="pb-2 font-medium text-right">% of Total</th>
              </tr>
            </thead>
            <tbody>
              {breakdown.map((row) => (
                <tr key={row.event_type} className="border-b border-border-subtle last:border-0">
                  <td className="py-2 font-mono text-xs text-txt">{row.event_type}</td>
                  <td className="py-2 text-right text-txt">{row.count.toLocaleString()}</td>
                  <td className="py-2 text-right text-txt-muted">{row.pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {/* Recent errors */}
      <Card className="p-5">
        <h2 className="text-sm font-semibold text-txt mb-4">Recent Route Errors</h2>
        {errors.length === 0 ? (
          <p className="text-txt-muted text-sm">No errors recorded.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-txt-muted border-b border-border-subtle">
                <th className="pb-2 font-medium">Timestamp</th>
                <th className="pb-2 font-medium">Route</th>
                <th className="pb-2 font-medium text-right">Status</th>
              </tr>
            </thead>
            <tbody>
              {errors.map((err) => (
                <tr key={err.id} className="border-b border-border-subtle last:border-0">
                  <td className="py-2 text-txt-muted text-xs">
                    {new Date(err.created_at).toLocaleString()}
                  </td>
                  <td className="py-2 font-mono text-xs text-txt">{err.route}</td>
                  <td className="py-2 text-right">
                    <span className="px-2 py-0.5 rounded text-xs bg-danger/10 text-danger font-medium">
                      {err.status_code}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {/* Per-user stats */}
      <Card className="p-5">
        <h2 className="text-sm font-semibold text-txt mb-4">Per-User Stats (last 30 days)</h2>
        {userStats.length === 0 ? (
          <p className="text-txt-muted text-sm">No users found.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-txt-muted border-b border-border-subtle">
                  <th className="pb-2 font-medium">Username</th>
                  <th className="pb-2 font-medium text-right">Events</th>
                  <th className="pb-2 font-medium text-right">AI Req.</th>
                  <th className="pb-2 font-medium text-right">AI Cost</th>
                  <th className="pb-2 font-medium text-right">Consent</th>
                </tr>
              </thead>
              <tbody>
                {userStats.map((u) => (
                  <tr key={u.user_id} className="border-b border-border-subtle last:border-0">
                    <td className="py-2 text-txt truncate max-w-[160px]">{u.username}</td>
                    <td className="py-2 text-right text-txt">{u.events_this_month.toLocaleString()}</td>
                    <td className="py-2 text-right text-txt">{u.ai_requests.toLocaleString()}</td>
                    <td className="py-2 text-right text-txt">${u.ai_cost_usd.toFixed(4)}</td>
                    <td className="py-2 text-right">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium ${
                          u.consent
                            ? "bg-green-500/10 text-green-600"
                            : "bg-gray-500/10 text-txt-muted"
                        }`}
                      >
                        {u.consent ? "Yes" : "No"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
