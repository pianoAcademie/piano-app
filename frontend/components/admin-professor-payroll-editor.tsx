"use client";

import { useMemo, useState } from "react";
import { localeForUiLanguage, type UiLanguage, uiText } from "../lib/ui-i18n";

type RateRule = {
  min_students: number;
  max_students: number | null;
  hourly_rate: string;
};

type RateGrid = {
  default_hourly_rate: string | null;
  rules: RateRule[];
};

type ActivityPayrollRow = {
  course_type_id: string;
  course_type_name: string;
  mode_label: string;
  reference_duration_minutes: number | null;
  initial_mode: "GENERAL" | "SPECIFIC";
  general_grid: RateGrid | null;
  specific_grid: RateGrid | null;
  specific_valid_from: string | null;
  specific_valid_to: string | null;
};

type Props = {
  professorId: string;
  effectiveFrom: string;
  currencyCode: string;
  availableCurrencies: string[];
  baseHourlyRate: string;
  activities: ActivityPayrollRow[];
  activeGeneralPeriodLabel: string | null;
  language: UiLanguage;
};

type EditableRule = {
  id: string;
  min: string;
  max: string;
  rate: string;
};

function normalizeMoneyInput(value: string): string {
  return value.replace(",", ".").trim();
}

function formatMoney(value: string | null, currencyCode: string, language: UiLanguage): string {
  if (!value) {
    return "-";
  }
  const amount = Number.parseFloat(value);
  if (!Number.isFinite(amount)) {
    return `${value} ${currencyCode}`;
  }
  try {
    return new Intl.NumberFormat(localeForUiLanguage(language), {
      style: "currency",
      currency: currencyCode || "EUR",
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currencyCode}`;
  }
}

function gridToEditableRules(grid: RateGrid | null): EditableRule[] {
  if (!grid || grid.rules.length === 0) {
    return [];
  }
  return grid.rules.map((rule, index) => ({
    id: `${index}-${rule.min_students}-${rule.max_students ?? "open"}`,
    min: String(rule.min_students),
    max: rule.max_students === null ? "" : String(rule.max_students),
    rate: String(rule.hourly_rate),
  }));
}

function buildDefaultRule(): EditableRule {
  return {
    id: `${Date.now()}-${Math.random()}`,
    min: "0",
    max: "",
    rate: "",
  };
}

function addRuleRow(previous: EditableRule[]): EditableRule[] {
  if (previous.length === 0) {
    return [buildDefaultRule()];
  }
  const sorted = [...previous].sort((a, b) => Number.parseInt(a.min || "0", 10) - Number.parseInt(b.min || "0", 10));
  const last = sorted[sorted.length - 1];
  const lastMax = Number.parseInt(last.max || "", 10);
  const nextMin = Number.isFinite(lastMax) ? String(lastMax + 1) : String(Number.parseInt(last.min || "0", 10) + 1);
  return [...previous, { id: `${Date.now()}-${Math.random()}`, min: nextMin, max: "", rate: "" }];
}

function resolveRate(grid: RateGrid | null, studentsCount: number): string | null {
  if (!grid) {
    return null;
  }
  const sortedRules = [...(grid.rules || [])].sort((a, b) => a.min_students - b.min_students);
  for (const rule of sortedRules) {
    if (studentsCount < rule.min_students) {
      continue;
    }
    if (rule.max_students !== null && studentsCount > rule.max_students) {
      continue;
    }
    return rule.hourly_rate;
  }
  return grid.default_hourly_rate;
}

function buildRuleLabel(rule: RateRule, currencyCode: string, language: UiLanguage): string {
  if (rule.max_students === null) {
    return uiText(language, "admin.professor_payroll.rule_open", {
      min: rule.min_students,
      amount: formatMoney(rule.hourly_rate, currencyCode, language),
    });
  }
  return uiText(language, "admin.professor_payroll.rule_range", {
    min: rule.min_students,
    max: rule.max_students,
    amount: formatMoney(rule.hourly_rate, currencyCode, language),
  });
}

function GridPreview({
  title,
  grid,
  currencyCode,
  language,
}: {
  title: string;
  grid: RateGrid | null;
  currencyCode: string;
  language: UiLanguage;
}): JSX.Element {
  return (
    <article className="prof-pay-preview">
      <p className="prof-pay-preview-title">{title}</p>
      {!grid ? <p className="muted">{uiText(language, "admin.professor_payroll.no_grid")}</p> : null}
      {grid && grid.rules.length === 0 ? (
        <p className="muted">{uiText(language, "admin.professor_payroll.single_rate", { amount: formatMoney(grid.default_hourly_rate, currencyCode, language) })}</p>
      ) : null}
      {grid && grid.rules.length > 0 ? (
        <ul className="prof-pay-rule-list">
          {grid.rules.map((rule, index) => (
            <li key={`${title}-rule-${index}`}>{buildRuleLabel(rule, currencyCode, language)}</li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

function RuleRowsEditor({
  rows,
  currencyCode,
  onChange,
  onAdd,
  onReset,
  resetLabel,
  language,
}: {
  rows: EditableRule[];
  currencyCode: string;
  onChange: (next: EditableRule[]) => void;
  onAdd: () => void;
  onReset: () => void;
  resetLabel: string;
  language: UiLanguage;
}): JSX.Element {
  return (
    <div className="prof-pay-grid-editor">
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>{uiText(language, "admin.professor_payroll.column_from")}</th>
              <th>{uiText(language, "admin.professor_payroll.column_to")}</th>
              <th>{uiText(language, "admin.professor_payroll.column_hourly_rate", { currency: currencyCode })}</th>
              <th>{uiText(language, "common.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={4} className="muted">
                  {uiText(language, "admin.professor_payroll.no_bracket")}
                </td>
              </tr>
            ) : null}
            {rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <input
                    type="number"
                    min={0}
                    step={1}
                    value={row.min}
                    onChange={(event) => {
                      onChange(
                        rows.map((candidate) =>
                          candidate.id === row.id
                            ? {
                                ...candidate,
                                min: event.target.value,
                              }
                            : candidate,
                        ),
                      );
                    }}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    min={0}
                    step={1}
                    value={row.max}
                    placeholder="+"
                    onChange={(event) => {
                      onChange(
                        rows.map((candidate) =>
                          candidate.id === row.id
                            ? {
                                ...candidate,
                                max: event.target.value,
                              }
                            : candidate,
                        ),
                      );
                    }}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    value={row.rate}
                    onChange={(event) => {
                      onChange(
                        rows.map((candidate) =>
                          candidate.id === row.id
                            ? {
                                ...candidate,
                                rate: event.target.value,
                              }
                            : candidate,
                        ),
                      );
                    }}
                  />
                </td>
                <td>
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => onChange(rows.filter((candidate) => candidate.id !== row.id))}
                  >
                    {uiText(language, "common.delete")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="row">
        <button type="button" className="ghost" onClick={onAdd}>
          {uiText(language, "admin.professor_payroll.add_bracket")}
        </button>
        <button type="button" className="ghost" onClick={onReset}>
          {resetLabel}
        </button>
      </div>
    </div>
  );
}

export default function AdminProfessorPayrollEditor({
  professorId,
  effectiveFrom,
  currencyCode,
  availableCurrencies,
  baseHourlyRate,
  activities,
  activeGeneralPeriodLabel,
  language,
}: Props): JSX.Element {
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const [activitySearch, setActivitySearch] = useState("");
  const [activityFilter, setActivityFilter] = useState<"ALL" | "INHERITED" | "OVERRIDDEN">("ALL");

  const [activityModes, setActivityModes] = useState<Record<string, "GENERAL" | "SPECIFIC">>(
    Object.fromEntries(activities.map((row) => [row.course_type_id, row.initial_mode])),
  );
  const [activityRules, setActivityRules] = useState<Record<string, EditableRule[]>>(
    Object.fromEntries(
      activities.map((row) => [
        row.course_type_id,
        row.specific_grid ? gridToEditableRules(row.specific_grid) : [],
      ]),
    ),
  );
  const [activityDefaultRates, setActivityDefaultRates] = useState<Record<string, string>>(
    Object.fromEntries(activities.map((row) => [row.course_type_id, row.specific_grid?.default_hourly_rate ?? ""])),
  );
  const [activityValidFrom, setActivityValidFrom] = useState<Record<string, string>>(
    Object.fromEntries(activities.map((row) => [row.course_type_id, row.specific_valid_from ?? effectiveFrom])),
  );
  const [activityValidTo, setActivityValidTo] = useState<Record<string, string>>(
    Object.fromEntries(activities.map((row) => [row.course_type_id, row.specific_valid_to ?? ""])),
  );

  const filteredActivities = useMemo(() => {
    const query = activitySearch.trim().toLowerCase();
    return activities.filter((row) => {
      const mode = activityModes[row.course_type_id] ?? row.initial_mode;
      if (activityFilter === "INHERITED" && mode === "SPECIFIC") {
        return false;
      }
      if (activityFilter === "OVERRIDDEN" && mode !== "SPECIFIC") {
        return false;
      }
      if (!query) {
        return true;
      }
      return row.course_type_name.toLowerCase().includes(query) || row.mode_label.toLowerCase().includes(query);
    });
  }, [activities, activityFilter, activityModes, activitySearch]);

  const overriddenCount = useMemo(
    () => Object.values(activityModes).filter((mode) => mode === "SPECIFIC").length,
    [activityModes],
  );

  return (
    <section className="prof-pay-editor">
      <input type="hidden" name="pay_ui_version" value="3" />
      <input type="hidden" name="professor_id" value={professorId} />

      <article className="card prof-pay-base-card">
        <div className="row spread">
          <h3>{t("admin.professor_payroll.base_title")}</h3>
          <span className="badge">{t("admin.professor_payroll.overrides_count", { count: overriddenCount })}</span>
        </div>
        <p className="muted">
          {t("admin.professor_payroll.base_help")}
        </p>
        {activeGeneralPeriodLabel ? (
          <p className="muted">{t("admin.professor_payroll.general_period", { period: activeGeneralPeriodLabel })}</p>
        ) : null}
        <div className="grid cols-3">
          <label>
            {t("admin.professor_payroll.effective_from")}
            <input type="date" name="effective_from" defaultValue={effectiveFrom} required />
          </label>
          <label>
            {t("admin.professor_payroll.currency")}
            <select name="currency_code" defaultValue={currencyCode}>
              {availableCurrencies.map((code) => (
                <option key={`pay-currency-${code}`} value={code}>
                  {code}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("admin.professor_payroll.base_hourly_rate")}
            <input type="number" name="base_hourly_rate" min="0" step="0.01" defaultValue={baseHourlyRate} required />
          </label>
        </div>
      </article>

      <article className="card prof-pay-activities-card">
        <div className="row spread">
          <h3>{t("admin.professor_payroll.activity_rules_title")}</h3>
          <span className="badge">{t("admin.professor_payroll.activities_count", { count: activities.length })}</span>
        </div>

        <div className="row top-gap-sm">
          <label className="prof-pay-search">
            {t("admin.professor_payroll.activity_search")}
            <input
              type="search"
              value={activitySearch}
              onChange={(event) => setActivitySearch(event.target.value)}
              placeholder={t("admin.professor_payroll.activity_search_placeholder")}
            />
          </label>
          <label>
            {t("common.filters")}
            <select value={activityFilter} onChange={(event) => setActivityFilter(event.target.value as "ALL" | "INHERITED" | "OVERRIDDEN") }>
              <option value="ALL">{t("admin.professor_payroll.filter_all")}</option>
              <option value="INHERITED">{t("admin.professor_payroll.filter_inherited")}</option>
              <option value="OVERRIDDEN">{t("admin.professor_payroll.filter_overridden")}</option>
            </select>
          </label>
        </div>

        <div className="prof-pay-activity-list top-gap-sm">
          {filteredActivities.map((activity) => {
            const mode = activityModes[activity.course_type_id] ?? activity.initial_mode;
            const specificRows = activityRules[activity.course_type_id] ?? [];
            const specificGrid: RateGrid = {
              default_hourly_rate: activityDefaultRates[activity.course_type_id]
                ? normalizeMoneyInput(activityDefaultRates[activity.course_type_id])
                : null,
              rules: specificRows
                .map((row) => {
                  const min = Number.parseInt(row.min, 10);
                  const max = row.max.trim() ? Number.parseInt(row.max, 10) : null;
                  const rate = normalizeMoneyInput(row.rate);
                  if (!Number.isFinite(min) || !rate) {
                    return null;
                  }
                  return {
                    min_students: min,
                    max_students: Number.isFinite(max as number) ? max : null,
                    hourly_rate: rate,
                  } satisfies RateRule;
                })
                .filter((row): row is RateRule => row !== null),
            };
            const activeGrid = mode === "SPECIFIC" ? specificGrid : activity.general_grid;

            return (
              <article key={`activity-pay-${activity.course_type_id}`} className="item prof-pay-activity-card">
                <input type="hidden" name="activity_course_type_id" value={activity.course_type_id} />
                <input type="hidden" name={`activity_rate_mode_${activity.course_type_id}`} value={mode} />

                <div className="row spread">
                  <div>
                    <strong>{activity.course_type_name}</strong>
                    <p className="muted">
                      {t("admin.professor_payroll.activity_meta", {
                        mode: activity.mode_label,
                        duration: activity.reference_duration_minutes ?? "-",
                      })}
                    </p>
                  </div>
                  <span className="badge">{mode === "SPECIFIC" ? t("admin.professor_payroll.override_badge") : t("admin.professor_payroll.general_badge")}</span>
                </div>

                <label className="top-gap-sm">
                  {t("admin.professor_payroll.pay_rule")}
                  <select
                    value={mode}
                    onChange={(event) => {
                      const nextMode = event.target.value as "GENERAL" | "SPECIFIC";
                      setActivityModes((previous) => ({ ...previous, [activity.course_type_id]: nextMode }));
                      if (nextMode === "SPECIFIC" && (activityRules[activity.course_type_id] ?? []).length === 0) {
                        const seedGrid = activity.general_grid ?? { default_hourly_rate: baseHourlyRate, rules: [] };
                        setActivityRules((previous) => ({
                          ...previous,
                          [activity.course_type_id]: gridToEditableRules(seedGrid),
                        }));
                        setActivityDefaultRates((previous) => ({
                          ...previous,
                          [activity.course_type_id]: seedGrid.default_hourly_rate ?? "",
                        }));
                        setActivityValidFrom((previous) => ({
                          ...previous,
                          [activity.course_type_id]: effectiveFrom,
                        }));
                      }
                    }}
                  >
                    <option value="GENERAL">{t("admin.professor_payroll.use_general_grid")}</option>
                    <option value="SPECIFIC">{t("admin.professor_payroll.define_override")}</option>
                  </select>
                </label>

                {mode === "SPECIFIC" ? (
                  <>
                    <div className="grid cols-2 top-gap-sm">
                      <label>
                        {t("admin.professor_payroll.override_start")}
                        <input
                          type="date"
                          value={activityValidFrom[activity.course_type_id] ?? effectiveFrom}
                          onChange={(event) =>
                            setActivityValidFrom((previous) => ({
                              ...previous,
                              [activity.course_type_id]: event.target.value,
                            }))
                          }
                          required
                        />
                      </label>
                      <label>
                        {t("admin.professor_payroll.override_end")}
                        <input
                          type="date"
                          value={activityValidTo[activity.course_type_id] ?? ""}
                          onChange={(event) =>
                            setActivityValidTo((previous) => ({
                              ...previous,
                              [activity.course_type_id]: event.target.value,
                            }))
                          }
                        />
                      </label>
                    </div>

                    <label>
                      {t("admin.professor_payroll.activity_base_rate")}
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={activityDefaultRates[activity.course_type_id] ?? ""}
                        onChange={(event) =>
                          setActivityDefaultRates((previous) => ({
                            ...previous,
                            [activity.course_type_id]: event.target.value,
                          }))
                        }
                      />
                    </label>

                    <RuleRowsEditor
                      rows={specificRows}
                      currencyCode={currencyCode}
                      onChange={(next) =>
                        setActivityRules((previous) => ({
                          ...previous,
                          [activity.course_type_id]: next,
                        }))
                      }
                      onAdd={() =>
                        setActivityRules((previous) => ({
                          ...previous,
                          [activity.course_type_id]: addRuleRow(previous[activity.course_type_id] ?? []),
                        }))
                      }
                      onReset={() => {
                        const seed = activity.general_grid;
                        setActivityRules((previous) => ({
                          ...previous,
                          [activity.course_type_id]: gridToEditableRules(seed),
                        }));
                        setActivityDefaultRates((previous) => ({
                          ...previous,
                          [activity.course_type_id]: seed?.default_hourly_rate ?? "",
                        }));
                      }}
                      resetLabel={t("admin.professor_payroll.reset_from_general")}
                      language={language}
                    />

                    <div className="grid cols-2 top-gap-sm">
                      <GridPreview
                        title={t("admin.professor_payroll.general_reference_grid")}
                        grid={activity.general_grid}
                        currencyCode={currencyCode}
                        language={language}
                      />
                      <GridPreview
                        title={t("admin.professor_payroll.teacher_override_grid")}
                        grid={specificGrid}
                        currencyCode={currencyCode}
                        language={language}
                      />
                    </div>

                    <input
                      type="hidden"
                      name={`activity_valid_from_${activity.course_type_id}`}
                      value={activityValidFrom[activity.course_type_id] ?? effectiveFrom}
                    />
                    <input
                      type="hidden"
                      name={`activity_valid_to_${activity.course_type_id}`}
                      value={activityValidTo[activity.course_type_id] ?? ""}
                    />
                    <input
                      type="hidden"
                      name={`activity_default_rate_${activity.course_type_id}`}
                      value={normalizeMoneyInput(activityDefaultRates[activity.course_type_id] ?? "")}
                    />
                    {specificRows.map((row) => (
                      <div key={`hidden-${activity.course_type_id}-${row.id}`}>
                        <input type="hidden" name={`activity_rule_min_${activity.course_type_id}`} value={row.min} />
                        <input type="hidden" name={`activity_rule_max_${activity.course_type_id}`} value={row.max} />
                        <input
                          type="hidden"
                          name={`activity_rule_rate_${activity.course_type_id}`}
                          value={normalizeMoneyInput(row.rate)}
                        />
                      </div>
                    ))}
                  </>
                ) : (
                  <div className="grid cols-2 top-gap-sm">
                    <GridPreview
                      title={t("admin.professor_payroll.applied_grid")}
                      grid={activity.general_grid}
                      currencyCode={currencyCode}
                      language={language}
                    />
                    <GridPreview
                      title={t("admin.professor_payroll.simulation")}
                      grid={activity.general_grid}
                      currencyCode={currencyCode}
                      language={language}
                    />
                  </div>
                )}

                <div className="prof-pay-simulation top-gap-sm">
                  <strong>{t("admin.professor_payroll.quick_simulation")}</strong>
                  <p className="muted">{t("admin.professor_payroll.simulation_students", { count: 2, amount: formatMoney(resolveRate(activeGrid, 2), currencyCode, language) })}</p>
                  <p className="muted">{t("admin.professor_payroll.simulation_students", { count: 4, amount: formatMoney(resolveRate(activeGrid, 4), currencyCode, language) })}</p>
                  <p className="muted">{t("admin.professor_payroll.simulation_students", { count: 6, amount: formatMoney(resolveRate(activeGrid, 6), currencyCode, language) })}</p>
                </div>
              </article>
            );
          })}
          {filteredActivities.length === 0 ? <p className="muted">{t("admin.professor_payroll.no_activity")}</p> : null}
        </div>
      </article>

      <div className="row prof-pay-submit-row">
        <button type="submit">{t("admin.professor_payroll.save")}</button>
      </div>
    </section>
  );
}
