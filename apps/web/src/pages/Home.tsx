import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { t } from "../i18n";

export function HomePage() {
  const { lang } = useAuth();
  return (
    <section className="hero">
      <h1 className="hero-brand">
        Pay<em>Loq</em>
      </h1>
      <p>{t("brandTagline", lang)}</p>
      <div className="cta-row">
        <Link className="btn btn-primary" to="/scenarios">
          {t("heroCta", lang)}
        </Link>
        <Link className="btn btn-ghost" to="/generate">
          {t("heroSecondary", lang)}
        </Link>
      </div>
    </section>
  );
}
