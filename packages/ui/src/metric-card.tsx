import type { ReactNode } from "react";

type MetricCardProps = {
  label: string;
  value: string;
  detail: string;
  icon: ReactNode;
};

export function MetricCard({ label, value, detail, icon }: MetricCardProps) {
  return (
    <section className="metric-card" aria-label={label}>
      <div className="metric-card__icon" aria-hidden="true">
        {icon}
      </div>
      <div>
        <p className="metric-card__label">{label}</p>
        <p className="metric-card__value">{value}</p>
        <p className="metric-card__detail">{detail}</p>
      </div>
    </section>
  );
}
