import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import NavBar from "./components/NavBar";
import Dashboard from "./pages/Dashboard";
import Insights from "./pages/Insights";
import LandingPage from "./pages/LandingPage";
import NotFound from "./pages/NotFound";
import RiskPrediction from "./pages/RiskPrediction";
import RiskQueue from "./pages/RiskQueue";

const tabs = [
  { to: "/dashboard", label: "Summary" },
  { to: "/risk-queue", label: "Risk Queue" },
  { to: "/prediction", label: "Prediction Studio" },
  { to: "/insights", label: "Model Insights" },
];

function pageHeading(pathname) {
  if (pathname.startsWith("/risk-queue")) {
    return "Risk Queue";
  }
  if (pathname.startsWith("/prediction")) {
    return "Prediction Studio";
  }
  if (pathname.startsWith("/insights")) {
    return "Model Insights";
  }
  return "Credit Risk Summary";
}

function isAppRoute(pathname) {
  return (
    pathname.startsWith("/dashboard") ||
    pathname.startsWith("/risk-queue") ||
    pathname.startsWith("/prediction") ||
    pathname.startsWith("/insights")
  );
}

/**
 * Wrapper that plays a page-transition animation on route change.
 */
function PageTransition({ children }) {
  const location = useLocation();
  return (
    <div key={location.pathname} className="page-transition-enter">
      {children}
    </div>
  );
}

export default function App() {
  const location = useLocation();
  const showShell = isAppRoute(location.pathname);

  if (!showShell) {
    return (
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    );
  }

  return (
    <div className="app-layout">
      <NavBar />

      <section className="workspace-shell">
        <header className="workspace-header">
          <div className="workspace-title-row">
            <div>
              <h1 className="workspace-title display-font">{pageHeading(location.pathname)}</h1>
              <p className="workspace-subtitle">
                Portfolio monitoring, borrower scoring, and collections decision support.
              </p>
            </div>
          </div>

          <nav className="workspace-tabs" aria-label="Workspace tabs">
            {tabs.map((tab) => (
              <NavLink
                key={tab.to}
                to={tab.to}
                className={({ isActive }) => ["tab-link", isActive ? "active" : ""].join(" ").trim()}
                end={tab.to === "/dashboard"}
              >
                {tab.label}
              </NavLink>
            ))}
          </nav>
        </header>

        <main className="workspace-content">
          <PageTransition>
            <Routes>
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/risk-queue" element={<RiskQueue />} />
              <Route path="/prediction" element={<RiskPrediction />} />
              <Route path="/insights" element={<Insights />} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </PageTransition>
        </main>
      </section>
    </div>
  );
}
