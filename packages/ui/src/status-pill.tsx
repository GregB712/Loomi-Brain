type StatusTone = "neutral" | "good" | "warn" | "bad";

type StatusPillProps = {
  children: string;
  tone?: StatusTone;
};

export function StatusPill({ children, tone = "neutral" }: StatusPillProps) {
  return <span className={`status-pill status-pill--${tone}`}>{children}</span>;
}
