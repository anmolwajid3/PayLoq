import { jsPDF } from "jspdf";
import type { CompanySession } from "../api";
import type { Lang } from "../i18n";
import { t } from "../i18n";

export function exportCompanyChatPdf(session: CompanySession, lang: Lang): void {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const margin = 14;
  const pageW = 210;
  const maxW = pageW - margin * 2;
  let y = margin;

  const write = (text: string, bold = false, size = 10) => {
    doc.setFont("helvetica", bold ? "bold" : "normal");
    doc.setFontSize(size);
    const lines = doc.splitTextToSize(text || "—", maxW) as string[];
    for (const line of lines) {
      if (y > 280) {
        doc.addPage();
        y = margin;
      }
      doc.text(line, margin, y);
      y += size * 0.45;
    }
    y += 2;
  };

  write("PayLoq", true, 16);
  write(t("companyData", lang), true, 13);
  write(
    `${t("sessionActive", lang)} · ${session.filenames.join(", ")}` +
      (session.model ? ` · ${session.model}` : ""),
    false,
    9,
  );
  write(
    `${t("expiresIn", lang)}: ${Math.round(session.ttl_remaining_s / 60)} min`,
    false,
    9,
  );

  if (session.situation_report) {
    write(t("situationReport", lang), true, 12);
    write(session.situation_report, false, 9);
  }

  write(t("chatTitle", lang), true, 12);
  if (!session.chat.length) {
    write("—");
  } else {
    for (const turn of session.chat) {
      write(
        turn.role === "user" ? t("customQuestion", lang) : t("answer", lang),
        true,
        10,
      );
      write(turn.content, false, 9);
    }
  }

  write(
    lang === "fi"
      ? "Istuntodata hävitetään uloskirjautumisessa tai vanhetessa — ei pysyvää tallennusta."
      : "Session data is discarded on logout or expiry — not stored permanently.",
    false,
    8,
  );

  doc.save(`payloq-company-chat.pdf`);
}
