import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import NavBar from "./components/NavBar";
import Dashboard from "./pages/Dashboard";
import Insights from "./pages/Insights";
import RiskPrediction from "./pages/RiskPrediction";
import RiskQueue from "./pages/RiskQueue";

const tabs = [
  { to: "/", label: "Summary" },
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

export default function App() {
  const location = useLocation();

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
                end={tab.to === "/"}
              >
                {tab.label}
              </NavLink>
            ))}
          </nav>
        </header>

        <main className="workspace-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/risk-queue" element={<RiskQueue />} />
            <Route path="/prediction" element={<RiskPrediction />} />
            <Route path="/insights" element={<Insights />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </section>
    </div>
  );
}
