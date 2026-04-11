import { useEffect, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { getUserRole, setUserRole } from "../api";

const links = [
  { to: "/", label: "Dashboard", icon: "▦" },
  { to: "/risk-queue", label: "Risk Queue", icon: "◉" },
  { to: "/prediction", label: "Prediction Studio", icon: "⟡" },
  { to: "/insights", label: "Model Insights", icon: "◎" },
];

export default function NavBar() {
  const navigate = useNavigate();
  const [quickFind, setQuickFind] = useState("");
  const [role, setRole] = useState("manager");

  useEffect(() => {
    setRole(getUserRole());
  }, []);

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
    <aside className="sidebar-shell">
      <div className="sidebar-brand">
        <span className="brand-badge">✦</span>
        <span className="brand-panel">◫</span>
      </div>

      <form className="quick-find" onSubmit={handleQuickFindSubmit}>
        <span aria-hidden="true">⌕</span>
        <input
          value={quickFind}
          onChange={(event) => setQuickFind(event.target.value)}
          placeholder="Quick Find"
          aria-label="Quick find"
        />
        <span className="quick-find-kbd">/</span>
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
  );
}
