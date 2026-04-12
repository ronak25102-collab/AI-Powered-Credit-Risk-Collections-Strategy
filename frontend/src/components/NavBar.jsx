import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useNavigate, useLocation } from "react-router-dom";
import { getUserRole, setUserRole } from "../api";

const links = [
  { to: "/dashboard", label: "Dashboard", icon: "▦" },
  { to: "/risk-queue", label: "Risk Queue", icon: "◉" },
  { to: "/prediction", label: "Prediction Studio", icon: "⟡" },
  { to: "/insights", label: "Model Insights", icon: "◎" },
];

export default function NavBar() {
  const navigate = useNavigate();
  const location = useLocation();
  const [quickFind, setQuickFind] = useState("");
  const [role, setRole] = useState("manager");
  const [mobileOpen, setMobileOpen] = useState(false);
  const quickFindRef = useRef(null);

  useEffect(() => {
    setRole(getUserRole());
  }, []);

  // Close mobile menu on route change
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  // Global keyboard shortcuts
  useEffect(() => {
    function handleKeyDown(e) {
      // Ctrl+K / Cmd+K → focus Quick Find
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        quickFindRef.current?.focus();
        // Open mobile menu if hidden
        setMobileOpen(true);
      }
      // Ctrl+Shift+N → navigate to Prediction Studio
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === "N") {
        e.preventDefault();
        navigate("/prediction");
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [navigate]);

  function handleQuickFindSubmit(event) {
    event.preventDefault();
    const value = quickFind.trim();
    if (!value) {
      navigate("/risk-queue");
      return;
    }
    navigate(`/risk-queue?search=${encodeURIComponent(value)}`);
  }

  return (
    <>
      {/* Mobile hamburger button */}
      <button
        type="button"
        className="mobile-hamburger"
        aria-label="Toggle navigation"
        onClick={() => setMobileOpen((prev) => !prev)}
      >
        <span className={`hamburger-icon ${mobileOpen ? "open" : ""}`}>
          <span />
          <span />
          <span />
        </span>
      </button>

      {/* Overlay */}
      {mobileOpen && (
        <div
          className="mobile-overlay"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      <aside className={`sidebar-shell ${mobileOpen ? "sidebar-open" : ""}`}>
        <div className="sidebar-brand">
          <Link to="/" className="brand-badge" aria-label="Back to home">✦</Link>
          <span className="brand-panel">◫</span>
        </div>

        <form className="quick-find" onSubmit={handleQuickFindSubmit}>
          <span aria-hidden="true">⌕</span>
          <input
            ref={quickFindRef}
            value={quickFind}
            onChange={(event) => setQuickFind(event.target.value)}
            placeholder="Quick Find"
            aria-label="Quick find (Ctrl+K)"
          />
          <span className="quick-find-kbd">⌘K</span>
        </form>

        <button type="button" className="sidebar-action" onClick={() => navigate("/prediction")}>
          <span aria-hidden="true">⊕</span>
          New Assessment
        </button>

        <div className="role-switcher-shell">
          <label className="role-switcher-label" htmlFor="role-switcher">Role</label>
          <select
            id="role-switcher"
            className="role-switcher-select"
            value={role}
            onChange={(event) => {
              const nextRole = event.target.value;
              setRole(nextRole);
              setUserRole(nextRole);
            }}
          >
            <option value="analyst">Analyst</option>
            <option value="agent">Collections Agent</option>
            <option value="manager">Manager</option>
          </select>
        </div>

        <nav className="sidebar-nav" aria-label="Primary">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) => ["side-link", isActive ? "active" : ""].join(" ").trim()}
            >
              <span aria-hidden="true">{link.icon}</span>
              <span>{link.label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>
    </>
  );
}
