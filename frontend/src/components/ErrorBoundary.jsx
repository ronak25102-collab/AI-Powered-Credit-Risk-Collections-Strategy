import { Component } from "react";
import { Link } from "react-router-dom";

/**
 * React Error Boundary.
 * Catches render-time errors and shows a friendly fallback UI
 * instead of a white screen.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("[ErrorBoundary]", error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary-page">
          <div className="error-boundary-content">
            <span className="error-boundary-icon">⚠</span>
            <h1 className="error-boundary-title display-font">Something Went Wrong</h1>
            <p className="error-boundary-desc">
              An unexpected error occurred. Please try refreshing the page.
            </p>
            {this.state.error && (
              <p className="error-boundary-detail">
                {this.state.error.message || "Unknown error"}
              </p>
            )}
            <div className="not-found-actions">
              <button
                type="button"
                className="landing-cta-primary"
                onClick={() => window.location.reload()}
              >
                Refresh Page
              </button>
              <Link to="/" className="landing-cta-secondary" onClick={this.handleReset}>
                Back to Home
              </Link>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
