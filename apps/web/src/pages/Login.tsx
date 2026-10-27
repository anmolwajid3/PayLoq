import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { t } from "../i18n";

export function LoginPage() {
  const { login, token, lang, setLang, ready } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("payloq");
  const [password, setPassword] = useState("payloq");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (ready && token) return <Navigate to="/" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-box">
        <div className="lang-toggle" style={{ marginBottom: "1rem" }}>
          <button type="button" className={lang === "fi" ? "active" : ""} onClick={() => setLang("fi")}>
            FI
          </button>
          <button type="button" className={lang === "en" ? "active" : ""} onClick={() => setLang("en")}>
            EN
          </button>
        </div>
        <h1>
          Pay<em>Loq</em>
        </h1>
        <p>{t("loginHint", lang)}</p>
        {error && <div className="error-banner">{error}</div>}
        <form className="form" onSubmit={onSubmit}>
          <label>
            {t("username", lang)}
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </label>
          <label>
            {t("password", lang)}
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </label>
          <button className="btn btn-primary" type="submit" disabled={busy}>
            {t("login", lang)}
          </button>
        </form>
      </div>
    </div>
  );
}
