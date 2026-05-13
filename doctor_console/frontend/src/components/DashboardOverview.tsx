import { Activity, Database, Gauge, Target } from "lucide-react";
import type { ReactNode } from "react";
import type { DashboardSummary } from "../types";

type Props = {
  summary?: DashboardSummary;
  loading: boolean;
};

export function DashboardOverview({ summary, loading }: Props) {
  if (!summary) {
    return (
      <section className="panel dashboard-panel">
        <div className="loading-bar">{loading ? "Loading dashboard..." : "No dashboard data."}</div>
      </section>
    );
  }

  return (
    <section className="panel dashboard-panel">
      <div className="panel-heading">
        <div>
          <div className="eyebrow">{summary.resultSet.label}</div>
          <h2>Cohort dashboard</h2>
        </div>
        <div className="dashboard-source mono">{summary.resultSet.path}</div>
      </div>

      <div className="kpi-grid">
        <KpiCard icon={<Activity size={19} />} label="Saved runs" value={String(summary.savedRuns)} detail={`${summary.totalGoldPatients} gold patients`} />
        <KpiCard icon={<Target size={19} />} label="DIRECT accuracy" value={formatRate(summary.directRate)} detail={`${summary.directMatches} direct matches`} />
        <KpiCard icon={<Gauge size={19} />} label="Clinical usefulness" value={formatRate(summary.usefulRate)} detail={`${summary.directMatches + summary.indirectMatches} direct or indirect`} />
        <KpiCard icon={<Database size={19} />} label="Semantic memory" value={String(summary.memoryStore.semanticEntries)} detail={summary.memoryStore.exists ? "entries indexed" : "store missing"} />
      </div>

      <div className="dashboard-grid">
        <div className="dashboard-block">
          <div className="block-heading">
            <h3>Match distribution</h3>
            <span>{summary.averageDurationS ? `${summary.averageDurationS}s avg` : "runtime unavailable"}</span>
          </div>
          <div className="bar-list">
            {summary.matchDistribution.map((item) => (
              <ProgressRow key={item.label} label={item.label} count={item.count} rate={item.rate} tone={item.label.toLowerCase()} />
            ))}
          </div>
        </div>

        <div className="dashboard-block">
          <div className="block-heading">
            <h3>Agent completion</h3>
            <span>{summary.savedRuns} runs</span>
          </div>
          <div className="completion-grid">
            {summary.agentCompletion.map((agent) => (
              <ProgressRow
                key={agent.agentId}
                label={agent.label}
                count={agent.completed}
                rate={agent.rate}
                tone={agent.rate >= 0.95 ? "direct" : agent.rate > 0 ? "indirect" : "miss"}
              />
            ))}
          </div>
        </div>

        <div className="dashboard-block top-diagnoses">
          <div className="block-heading">
            <h3>Most common final diagnoses</h3>
            <span>top {summary.topDiagnoses.length}</span>
          </div>
          {summary.topDiagnoses.length ? (
            summary.topDiagnoses.map((item) => (
              <div className="diagnosis-row" key={item.diagnosis}>
                <strong>{item.diagnosis}</strong>
                <span>{item.count}</span>
              </div>
            ))
          ) : (
            <div className="empty-state">No final diagnoses saved.</div>
          )}
        </div>
      </div>
    </section>
  );
}

function KpiCard({ icon, label, value, detail }: { icon: ReactNode; label: string; value: string; detail: string }) {
  return (
    <div className="kpi-card">
      <div className="kpi-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function ProgressRow({ label, count, rate, tone }: { label: string; count: number; rate: number; tone: string }) {
  return (
    <div className="progress-row">
      <div className="progress-meta">
        <span>{label}</span>
        <strong>{count} | {formatRate(rate)}</strong>
      </div>
      <div className="progress-track">
        <div className={`progress-fill tone-${tone}`} style={{ width: `${Math.round(rate * 100)}%` }} />
      </div>
    </div>
  );
}

function formatRate(value: number) {
  return `${Math.round(value * 100)}%`;
}
