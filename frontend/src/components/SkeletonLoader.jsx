/**
 * Skeleton loader for the dashboard.
 * Shows card-shaped placeholders that pulse while data loads.
 */
export default function SkeletonLoader() {
  return (
    <div className="skeleton-layout fade-up">
      {/* Hero card skeleton */}
      <div className="skeleton-card skeleton-hero">
        <div className="skeleton-line skeleton-line-sm" style={{ width: "35%" }} />
        <div className="skeleton-line skeleton-line-lg" style={{ width: "65%" }} />
        <div className="skeleton-line skeleton-line-md" style={{ width: "80%" }} />
      </div>

      {/* KPI row skeleton */}
      <div className="skeleton-kpi-row">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="skeleton-card skeleton-kpi">
            <div className="skeleton-line skeleton-line-sm" style={{ width: "60%" }} />
            <div className="skeleton-line skeleton-line-lg" style={{ width: "40%" }} />
            <div className="skeleton-line skeleton-line-sm" style={{ width: "75%" }} />
          </div>
        ))}
      </div>

      {/* Main content skeleton */}
      <div className="skeleton-main-row">
        <div className="skeleton-card skeleton-chart">
          <div className="skeleton-line skeleton-line-sm" style={{ width: "45%" }} />
          <div className="skeleton-rect" />
        </div>
        <div className="skeleton-card skeleton-side">
          <div className="skeleton-line skeleton-line-sm" style={{ width: "50%" }} />
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className="skeleton-feed-item">
              <div className="skeleton-line skeleton-line-md" style={{ width: "70%" }} />
              <div className="skeleton-line skeleton-line-sm" style={{ width: "55%" }} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
