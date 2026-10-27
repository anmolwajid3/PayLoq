import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth";
import { t } from "../i18n";

export function Layout() {
  const { username, lang, setLang, logout } = useAuth();

  return (
    <div className="app-shell">
      <header className="topbar">
        <NavLink to="/" className="brand">
          Pay<em>Loq</em>
        </NavLink>
        <nav className="nav">
          <NavLink to="/scenarios" className={({ isActive }) => (isActive ? "active" : "")}>
            {t("scenarios", lang)}
          </NavLink>
          <NavLink to="/generate" className={({ isActive }) => (isActive ? "active" : "")}>
            {t("generate", lang)}
          </NavLink>
          <NavLink to="/runs" className={({ isActive }) => (isActive ? "active" : "")}>
            {t("runs", lang)}
          </NavLink>
          <div className="lang-toggle" aria-label="Language">
            <button
              type="button"
              className={lang === "fi" ? "active" : ""}
              onClick={() => setLang("fi")}
            >
              FI
            </button>
            <button
              type="button"
              className={lang === "en" ? "active" : ""}
              onClick={() => setLang("en")}
            >
              EN
            </button>
          </div>
          {username && (
            <button type="button" className="btn btn-ghost" onClick={logout}>
              {t("logout", lang)}
            </button>
          )}
        </nav>
      </header>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
