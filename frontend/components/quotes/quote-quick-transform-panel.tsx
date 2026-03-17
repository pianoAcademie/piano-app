import Link from "next/link";

import ConfirmSubmitButton from "../confirm-submit-button";
import type { QuoteQuickTransformAnalysis } from "../../lib/quote-transformation";

type QuoteQuickTransformPanelProps = {
  quoteId: string;
  currency: string;
  analysis: QuoteQuickTransformAnalysis;
  transformBasePath: string;
  returnTo: string;
  scenarioLinks: Array<{
    key: "live" | "A" | "B" | "C";
    label: string;
    href: string;
    active: boolean;
  }>;
  quickTransformAction: (formData: FormData) => Promise<void>;
};

function formatAmount(value: number, currency: string): string {
  try {
    return new Intl.NumberFormat("fr-FR", { style: "currency", currency: currency || "EUR" }).format(value);
  } catch {
    return `${value.toFixed(2)} ${(currency || "EUR").toUpperCase()}`;
  }
}

function statusMeta(status: QuoteQuickTransformAnalysis["status"]): {
  label: string;
  className: string;
} {
  if (status === "auto_validable") {
    return { label: "Auto-validable", className: "status-ok" };
  }
  if (status === "review_required") {
    return { label: "A verifier", className: "status-warn" };
  }
  return { label: "Bloque", className: "quote-transform-status-blocked" };
}

export default function QuoteQuickTransformPanel({
  quoteId,
  currency,
  analysis,
  transformBasePath,
  returnTo,
  scenarioLinks,
  quickTransformAction,
}: QuoteQuickTransformPanelProps): JSX.Element {
  const status = statusMeta(analysis.status);
  const firstStep = analysis.firstNonConformStep || 1;
  const wizardReviewHref = `${transformBasePath}&step=${firstStep}`;
  const summary = analysis.summary;
  const formId = `quote-quick-transform-${quoteId}`;

  const quickDescription = [
    `Client: ${analysis.proposedClient?.displayName || "-"}`,
    `Activites: ${summary.activitiesCount}`,
    `Creneaux auto-assignables: ${summary.autoAssignableCount}/${summary.activitiesCount}`,
    `Totaux: devis ${formatAmount(summary.totalQuoteTtc, currency)} · systeme ${formatAmount(summary.totalSystemTtc, currency)}`,
    "Le systeme reverifiera la capacite des creneaux juste avant execution et un rollback admin restera possible si une correction est necessaire.",
  ].join(" \n");

  return (
    <section className="card quote-quick-transform-card">
      <div className="row spread wrap gap-sm">
        <div>
          <h3>Transformation rapide</h3>
          <p className="muted">Decision immediate avant ouverture du wizard complet.</p>
        </div>
        <span className={`status-pill ${status.className}`}>{status.label}</span>
      </div>

      <div className="quote-quick-transform-summary top-gap-sm">
        <p><strong>Client propose:</strong> {analysis.proposedClient?.displayName || "-"}</p>
        <p><strong>Activites:</strong> {summary.activitiesCount}</p>
        <p><strong>Creneaux trouves:</strong> {summary.slotsFoundCount} / {summary.activitiesCount}</p>
        <p><strong>Creneaux auto-assignables:</strong> {summary.autoAssignableCount} / {summary.activitiesCount}</p>
        <p><strong>Hors planning:</strong> {summary.offPlanningCount}</p>
        <p><strong>Total devis:</strong> {formatAmount(summary.totalQuoteTtc, currency)}</p>
        <p><strong>Total systeme:</strong> {formatAmount(summary.totalSystemTtc, currency)}</p>
      </div>

      <div className="top-gap-sm">
        <p className="muted">Scenarios localhost</p>
        <div className="quote-transform-scenario-list">
          {scenarioLinks.map((item) => (
            <Link
              key={`quick-scenario-${item.key}`}
              href={item.href}
              className={`quote-transform-scenario-link ${item.active ? "active" : ""}`}
            >
              {item.label}
            </Link>
          ))}
        </div>
      </div>

      <div className="grid cols-3 top-gap-sm quote-quick-transform-reasons">
        <article className="item">
          <h4>OK</h4>
          {analysis.reasonsOk.length === 0 ? <p className="muted">-</p> : null}
          {analysis.reasonsOk.slice(0, 4).map((message, index) => (
            <p key={`quick-ok-${index}`} className="muted">- {message}</p>
          ))}
        </article>
        <article className="item">
          <h4>Warnings</h4>
          {analysis.warnings.length === 0 ? <p className="muted">-</p> : null}
          {analysis.warnings.slice(0, 4).map((message, index) => (
            <p key={`quick-warn-${index}`} className="flash-warn">- {message}</p>
          ))}
        </article>
        <article className="item">
          <h4>Blocages</h4>
          {analysis.blockingIssues.length === 0 ? <p className="muted">-</p> : null}
          {analysis.blockingIssues.slice(0, 4).map((message, index) => (
            <p key={`quick-block-${index}`} className="flash-err">- {message}</p>
          ))}
        </article>
      </div>

      <div className="row wrap gap-sm top-gap-sm">
        {analysis.status === "auto_validable" ? (
          <>
            <form id={formId} action={quickTransformAction}>
              <input type="hidden" name="quote_id" value={quoteId} />
              <input type="hidden" name="return_to" value={returnTo} />
            </form>
            <ConfirmSubmitButton
              formId={formId}
              label="Transformer directement"
              title="Confirmer la transformation rapide ?"
              description={quickDescription}
              confirmLabel="Executer l'integration"
            />
          </>
        ) : null}

        {analysis.status === "review_required" ? (
          <Link className="ghost" href={wizardReviewHref}>
            Verifier avant transformation
          </Link>
        ) : null}

        {analysis.status === "blocked" ? (
          <Link className="ghost" href={wizardReviewHref}>
            Ouvrir le wizard
          </Link>
        ) : null}

        <Link className="ghost" href={transformBasePath}>
          Ouvrir le wizard complet
        </Link>
      </div>
    </section>
  );
}
