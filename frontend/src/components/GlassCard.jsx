export default function GlassCard({
  title,
  subtitle,
  children,
  className = "",
  strong = false,
}) {
  return (
    <section
      className={`${strong ? "glass-card-strong" : "glass-card"} rounded-2xl p-5 sm:p-6 ${className}`}
    >
      {(title || subtitle) && (
        <header className="mb-4">
          {title && <h3 className="display-font text-lg font-semibold text-[var(--text-main)]">{title}</h3>}
          {subtitle && <p className="mt-1 text-sm text-[var(--text-muted)]">{subtitle}</p>}
        </header>
      )}
      {children}
    </section>
  );
}
