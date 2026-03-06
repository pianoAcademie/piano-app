"use client";

import { useMemo, useState } from "react";

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

function formatMoney(value: string | null, currencyCode: string): string {
  if (!value) {
    return "-";
  }
  const amount = Number.parseFloat(value);
  if (!Number.isFinite(amount)) {
    return `${value} ${currencyCode}`;
  }
  return `${amount.toFixed(2).replace(".", ",")} ${currencyCode}`;
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

function buildRuleLabel(rule: RateRule, currencyCode: string): string {
  if (rule.max_students === null) {
    return `${rule.min_students} eleves et + : ${formatMoney(rule.hourly_rate, currencyCode)}`;
  }
  return `${rule.min_students} a ${rule.max_students} eleves : ${formatMoney(rule.hourly_rate, currencyCode)}`;
}

function GridPreview({ title, grid, currencyCode }: { title: string; grid: RateGrid | null; currencyCode: string }): JSX.Element {
  return (
    <article className="prof-pay-preview">
      <p className="prof-pay-preview-title">{title}</p>
      {!grid ? <p className="muted">Aucune grille definie.</p> : null}
      {grid && grid.rules.length === 0 ? (
        <p className="muted">Taux unique: {formatMoney(grid.default_hourly_rate, currencyCode)}</p>
      ) : null}
      {grid && grid.rules.length > 0 ? (
        <ul className="prof-pay-rule-list">
          {grid.rules.map((rule, index) => (
            <li key={`${title}-rule-${index}`}>{buildRuleLabel(rule, currencyCode)}</li>
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
}: {
  rows: EditableRule[];
  currencyCode: string;
  onChange: (next: EditableRule[]) => void;
  onAdd: () => void;
  onReset: () => void;
  resetLabel: string;
}): JSX.Element {
  return (
    <div className="prof-pay-grid-editor">
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>De</th>
              <th>A</th>
              <th>Taux horaire ({currencyCode})</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={4} className="muted">
                  Aucune tranche definie.
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
                    Supprimer
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="row">
        <button type="button" className="ghost" onClick={onAdd}>
          Ajouter une tranche
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
}: Props): JSX.Element {
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
          <h3>1. Paie de base</h3>
          <span className="badge">{overriddenCount} surcouche(s) active(s)</span>
        </div>
        <p className="muted">
          Ce taux s applique uniquement si aucune grille generale active ni surcouche par activite n est applicable.
        </p>
        {activeGeneralPeriodLabel ? (
          <p className="muted">Periode de grille generale active: {activeGeneralPeriodLabel}</p>
        ) : null}
        <div className="grid cols-3">
          <label>
            Date de prise d effet
            <input type="date" name="effective_from" defaultValue={effectiveFrom} required />
          </label>
          <label>
            Devise
            <select name="currency_code" defaultValue={currencyCode}>
              {availableCurrencies.map((code) => (
                <option key={`pay-currency-${code}`} value={code}>
                  {code}
                </option>
              ))}
            </select>
          </label>
          <label>
            Taux horaire de base
            <input type="number" name="base_hourly_rate" min="0" step="0.01" defaultValue={baseHourlyRate} required />
          </label>
        </div>
      </article>

      <article className="card prof-pay-activities-card">
        <div className="row spread">
          <h3>2. Regles par activite</h3>
          <span className="badge">{activities.length} activite(s)</span>
        </div>

        <div className="row top-gap-sm">
          <label className="prof-pay-search">
            Recherche activite
            <input
              type="search"
              value={activitySearch}
              onChange={(event) => setActivitySearch(event.target.value)}
              placeholder="Nom ou mode"
            />
          </label>
          <label>
            Filtre
            <select value={activityFilter} onChange={(event) => setActivityFilter(event.target.value as "ALL" | "INHERITED" | "OVERRIDDEN") }>
              <option value="ALL">Toutes</option>
              <option value="INHERITED">Heritees</option>
              <option value="OVERRIDDEN">Surchargees</option>
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
                      {activity.mode_label} | Duree ref: {activity.reference_duration_minutes ?? "-"} min
                    </p>
                  </div>
                  <span className="badge">{mode === "SPECIFIC" ? "Surcouche professeur" : "Grille generale"}</span>
                </div>

                <label className="top-gap-sm">
                  Regle de paie
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
                    <option value="GENERAL">Utiliser la grille generale</option>
                    <option value="SPECIFIC">Definir une surcouche professeur</option>
                  </select>
                </label>

                {mode === "SPECIFIC" ? (
                  <>
                    <div className="grid cols-2 top-gap-sm">
                      <label>
                        Date debut surcouche
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
                        Date fin surcouche (optionnel)
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
                      Taux de base de l activite (fallback)
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
                      resetLabel="Reinitialiser depuis la grille generale"
                    />

                    <div className="grid cols-2 top-gap-sm">
                      <GridPreview title="Grille generale de reference" grid={activity.general_grid} currencyCode={currencyCode} />
                      <GridPreview title="Surcouche professeur" grid={specificGrid} currencyCode={currencyCode} />
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
                    <GridPreview title="Grille appliquee" grid={activity.general_grid} currencyCode={currencyCode} />
                    <GridPreview title="Simulation" grid={activity.general_grid} currencyCode={currencyCode} />
                  </div>
                )}

                <div className="prof-pay-simulation top-gap-sm">
                  <strong>Simulation rapide</strong>
                  <p className="muted">2 eleves: {formatMoney(resolveRate(activeGrid, 2), currencyCode)}</p>
                  <p className="muted">4 eleves: {formatMoney(resolveRate(activeGrid, 4), currencyCode)}</p>
                  <p className="muted">6 eleves: {formatMoney(resolveRate(activeGrid, 6), currencyCode)}</p>
                </div>
              </article>
            );
          })}
          {filteredActivities.length === 0 ? <p className="muted">Aucune activite ne correspond a ce filtre.</p> : null}
        </div>
      </article>

      <div className="row prof-pay-submit-row">
        <button type="submit">Enregistrer la configuration de paie</button>
      </div>
    </section>
  );
}
