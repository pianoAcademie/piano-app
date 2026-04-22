import Link from "next/link";

import ConfirmSubmitButton from "../confirm-submit-button";
import type { QuoteQuickTransformAnalysis } from "../../lib/quote-transformation";
import { localeForUiLanguage, type UiLanguage, uiText } from "../../lib/ui-i18n";

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
  language?: UiLanguage;
};

function formatAmount(value: number, currency: string, language: UiLanguage): string {
  try {
    return new Intl.NumberFormat(localeForUiLanguage(language), { style: "currency", currency: currency || "EUR" }).format(value);
  } catch {
    return `${value.toFixed(2)} ${(currency || "EUR").toUpperCase()}`;
  }
}

function statusMeta(status: QuoteQuickTransformAnalysis["status"], language: UiLanguage): {
  label: string;
  className: string;
} {
  if (status === "auto_validable") {
    return { label: uiText(language, "admin.quote_detail.quick_transform.status_auto_validable"), className: "status-ok" };
  }
  if (status === "review_required") {
    return { label: uiText(language, "admin.quote_detail.quick_transform.status_review_required"), className: "status-warn" };
  }
  return { label: uiText(language, "admin.quote_detail.quick_transform.status_blocked"), className: "quote-transform-status-blocked" };
}

export default function QuoteQuickTransformPanel({
  quoteId,
  currency,
  analysis,
  transformBasePath,
  returnTo,
  scenarioLinks,
  quickTransformAction,
  language = "fr",
}: QuoteQuickTransformPanelProps): JSX.Element {
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const status = statusMeta(analysis.status, language);
  const firstStep = analysis.firstNonConformStep || 1;
  const wizardReviewHref = `${transformBasePath}&step=${firstStep}`;
  const summary = analysis.summary;
  const formId = `quote-quick-transform-${quoteId}`;

  const quickDescription = [
    t("admin.quote_detail.quick_transform.desc_client", { client: analysis.proposedClient?.displayName || "-" }),
    t("admin.quote_detail.quick_transform.desc_activities", { count: summary.activitiesCount }),
    t("admin.quote_detail.quick_transform.desc_auto_assignable", {
      count: summary.autoAssignableCount,
      total: summary.activitiesCount,
    }),
    t("admin.quote_detail.quick_transform.desc_totals", {
      quote: formatAmount(summary.totalQuoteTtc, currency, language),
      system: formatAmount(summary.totalSystemTtc, currency, language),
    }),
    t("admin.quote_detail.quick_transform.desc_recheck"),
  ].join(" \n");

  return (
    <section className="card quote-quick-transform-card">
      <div className="row spread wrap gap-sm">
        <div>
          <h3>{t("admin.quote_detail.quick_transform.title")}</h3>
          <p className="muted">{t("admin.quote_detail.quick_transform.subtitle")}</p>
        </div>
        <span className={`status-pill ${status.className}`}>{status.label}</span>
      </div>

      <div className="quote-quick-transform-summary top-gap-sm">
        <p><strong>{t("admin.quote_detail.quick_transform.proposed_client")}:</strong> {analysis.proposedClient?.displayName || "-"}</p>
        <p><strong>{t("admin.quote_detail.quick_transform.activities")}:</strong> {summary.activitiesCount}</p>
        <p><strong>{t("admin.quote_detail.quick_transform.slots_found")}:</strong> {summary.slotsFoundCount} / {summary.activitiesCount}</p>
        <p><strong>{t("admin.quote_detail.quick_transform.auto_assignable")}:</strong> {summary.autoAssignableCount} / {summary.activitiesCount}</p>
        <p><strong>{t("admin.quote_detail.quick_transform.off_planning")}:</strong> {summary.offPlanningCount}</p>
        <p><strong>{t("admin.quote_detail.quick_transform.total_quote")}:</strong> {formatAmount(summary.totalQuoteTtc, currency, language)}</p>
        <p><strong>{t("admin.quote_detail.quick_transform.total_system")}:</strong> {formatAmount(summary.totalSystemTtc, currency, language)}</p>
      </div>

      <div className="top-gap-sm">
        <p className="muted">{t("admin.quote_detail.quick_transform.localhost_scenarios")}</p>
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
          <h4>{t("admin.quote_detail.quick_transform.ok")}</h4>
          {analysis.reasonsOk.length === 0 ? <p className="muted">-</p> : null}
          {analysis.reasonsOk.slice(0, 4).map((message, index) => (
            <p key={`quick-ok-${index}`} className="muted">- {message}</p>
          ))}
        </article>
        <article className="item">
          <h4>{t("admin.quote_detail.quick_transform.warnings")}</h4>
          {analysis.warnings.length === 0 ? <p className="muted">-</p> : null}
          {analysis.warnings.slice(0, 4).map((message, index) => (
            <p key={`quick-warn-${index}`} className="flash-warn">- {message}</p>
          ))}
        </article>
        <article className="item">
          <h4>{t("admin.quote_detail.quick_transform.blocking_issues")}</h4>
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
              label={t("admin.quote_detail.quick_transform.transform_directly")}
              title={t("admin.quote_detail.quick_transform.confirm_title")}
              description={quickDescription}
              confirmLabel={t("admin.quote_detail.quick_transform.confirm_execute")}
            />
          </>
        ) : null}

        {analysis.status === "review_required" ? (
          <Link className="ghost" href={wizardReviewHref}>
            {t("admin.quote_detail.quick_transform.review_before_transform")}
          </Link>
        ) : null}

        {analysis.status === "blocked" ? (
          <Link className="ghost" href={wizardReviewHref}>
            {t("admin.quote_detail.quick_transform.open_wizard")}
          </Link>
        ) : null}

        <Link className="ghost" href={transformBasePath}>
          {t("admin.quote_detail.quick_transform.open_full_wizard")}
        </Link>
      </div>
    </section>
  );
}
