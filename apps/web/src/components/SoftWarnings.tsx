import type { Lang } from "../i18n";
import { t } from "../i18n";

export type SoftWarning = {
  code: string;
  severity?: string;
  message_fi?: string;
  message_en?: string;
  message?: string;
};

type Props = {
  warnings: SoftWarning[];
  lang: Lang;
  title?: string;
  hint?: string;
};

export function SoftWarnings({ warnings, lang, title, hint }: Props) {
  if (!warnings.length) return null;
  return (
    <div className="soft-banner" role="status">
      <div className="soft-banner-head">
        <strong>{title || t("softWarnings", lang)}</strong>
        <span className="muted">{hint || t("softWarningsHint", lang)}</span>
      </div>
      <ul className="soft-list">
        {warnings.map((w) => {
          const msg =
            (lang === "fi" ? w.message_fi : w.message_en) ||
            w.message ||
            w.message_en ||
            w.message_fi ||
            w.code;
          return (
            <li key={w.code + msg}>
              <span className="soft-code">{w.code}</span>
              {msg}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

type Issue = { code: string; message: string; severity: string };

export function ValidationPanel({
  issues,
  lang,
}: {
  issues: Issue[];
  lang: Lang;
}) {
  const errors = issues.filter((i) => i.severity === "error");
  const warnings = issues.filter((i) => i.severity !== "error");

  return (
    <div className="panel">
      <h3>{t("validation", lang)}</h3>
      {!issues.length && <p className="status-ok">{t("noIssues", lang)}</p>}

      {errors.length > 0 && (
        <div className="issue-group">
          <h4>{t("validationErrors", lang)}</h4>
          {errors.map((issue) => (
            <div key={`${issue.code}-${issue.message}`} className="issue error">
              <span className="issue-tag">{t("severityError", lang)}</span>
              {issue.code}: {issue.message}
            </div>
          ))}
        </div>
      )}

      {warnings.length > 0 && (
        <div className="issue-group">
          <h4>{t("validationWarnings", lang)}</h4>
          {warnings.map((issue) => (
            <div key={`${issue.code}-${issue.message}`} className="issue warning">
              <span className="issue-tag warn">{t("severityWarning", lang)}</span>
              {issue.code}: {issue.message}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
