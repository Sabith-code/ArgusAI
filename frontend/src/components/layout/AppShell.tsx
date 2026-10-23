import { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { api } from '../../api';
import './AppShell.css';

export function AppShell({ children }: { children: React.ReactNode }) {
  const [healthy, setHealthy] = useState<boolean | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  useEffect(() => {
    api.getHealth()
      .then(() => setHealthy(true))
      .catch(() => setHealthy(false));
  }, []);

  return (
    <div className="app-shell">
      <header className="topnav">
        <div className="topnav__left">
          <button className="topnav__toggle" onClick={() => setSidebarOpen(!sidebarOpen)} aria-label="Toggle sidebar">
            ☰
          </button>
          <span className="topnav__logo">🛡 Brand Monitor</span>
        </div>
        <div className="topnav__right">
          <span className={`health-dot ${healthy === true ? 'health-dot--ok' : healthy === false ? 'health-dot--err' : 'health-dot--loading'}`} />
          <span className="health-label">{healthy === true ? 'API Connected' : healthy === false ? 'API Offline' : 'Checking...'}</span>
        </div>
      </header>

      <div className="app-body">
        <aside className={`sidebar ${sidebarOpen ? 'sidebar--open' : 'sidebar--closed'}`}>
          <nav className="sidebar__nav">
            <NavLink to="/" end className={({ isActive }) => `sidebar__link ${isActive ? 'sidebar__link--active' : ''}`}>
              <span className="sidebar__icon">📊</span> Dashboard
            </NavLink>
            <NavLink to="/mentions" className={({ isActive }) => `sidebar__link ${isActive ? 'sidebar__link--active' : ''}`}>
              <span className="sidebar__icon">📰</span> Mentions
            </NavLink>
            <NavLink to="/events" className={({ isActive }) => `sidebar__link ${isActive ? 'sidebar__link--active' : ''}`}>
              <span className="sidebar__icon">🔗</span> Events
            </NavLink>
            <NavLink to="/signals" className={({ isActive }) => `sidebar__link ${isActive ? 'sidebar__link--active' : ''}`}>
              <span className="sidebar__icon">⚡</span> Signals
            </NavLink>
          </nav>
        </aside>

        <main className="main-content">
          {children}
        </main>
      </div>
    </div>
  );
}
