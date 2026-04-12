import GlassCard from "./GlassCard";

export default function KpiCard({ title, value, subtext, accent = "text-[var(--text-main)]", children }) {
  return (
    <GlassCard className="h-full border-orange-200/30 transition duration-300 hover:-translate-y-1.5">
      <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-muted)]">{title}</p>
      <p className={`mt-3 display-font text-3xl font-semibold ${accent}`}>{value}</p>
      {subtext ? <p className="mt-2 text-sm text-[var(--text-muted)]">{subtext}</p> : null}
      {children}
    </GlassCard>
  );
}
