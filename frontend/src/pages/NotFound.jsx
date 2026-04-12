import { Link } from "react-router-dom";

/**
 * Themed 404 page.
 */
export default function NotFound() {
  return (
    <div className="not-found-page">
      <div className="not-found-content">
        <span className="not-found-code display-font">404</span>
        <h1 className="not-found-title display-font">Page Not Found</h1>
        <p className="not-found-desc">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="not-found-actions">
          <Link to="/" className="landing-cta-primary">
            Back to Home
            <span className="landing-cta-arrow" aria-hidden="true">→</span>
          </Link>
          <Link to="/dashboard" className="landing-cta-secondary">
            Go to Dashboard
          </Link>
        </div>
      </div>
    </div>
  );
}
