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
  initial_mode: "GENERAL" | "PROFESSOR" | "SPECIFIC";
  general_grid: RateGrid | null;
  specific_grid: RateGrid | null;
};

type Props = {
  professorId: string;
  effectiveFrom: string;
  currencyCode: string;
  availableCurrencies: string[];
  baseHourlyRate: string;
  professorHasOverride: boolean;
  professorGrid: RateGrid | null;
  professorReferenceGrid: RateGrid | null;
  activities: ActivityPayrollRow[];
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
  professorHasOverride,
  professorGrid,
  professorReferenceGrid,
  activities,
}: Props): JSX.Element {
  const initialProfessorRules = professorHasOverride ? gridToEditableRules(professorGrid) : [];
  const [profGridMode, setProfGridMode] = useState<"inherit" | "override">(professorHasOverride ? "override" : "inherit");
  const [profRules, setProfRules] = useState<EditableRule[]>(initialProfessorRules);
  const [activitySearch, setActivitySearch] = useState("");
  const [activityFilter, setActivityFilter] = useState<"ALL" | "INHERITED" | "OVERRIDDEN">("ALL");

  const [activityModes, setActivityModes] = useState<Record<string, "GENERAL" | "PROFESSOR" | "SPECIFIC">>(
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
    Object.fromEntries(
      activities.map((row) => [row.course_type_id, row.specific_grid?.default_hourly_rate ?? ""]),
    ),
  );

  const resolvedProfessorGrid: RateGrid | null = useMemo(() => {
    if (profGridMode !== "override") {
      return null;
    }
    return {
      default_hourly_rate: baseHourlyRate,
      rules: profRules
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
  }, [profGridMode, profRules, baseHourlyRate]);

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

  return (
    <section className="prof-pay-editor">
      <input type="hidden" name="pay_ui_version" value="2" />
      <input type="hidden" name="professor_id" value={professorId} />

      <article className="card prof-pay-base-card">
        <h3>1. Paie de base</h3>
        <p className="muted">
          Ce taux s applique uniquement si aucune grille par nombre d eleves ni aucune regle specifique d activite n est definie.
        </p>
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

      <article className="card prof-pay-prof-grid-card">
        <div className="row spread">
          <h3>2. Grille professeur</h3>
          <span className="badge">{profGridMode === "override" ? "Surcouche professeur active" : "Herite de la grille generale"}</span>
        </div>

        <input type="hidden" name="prof_grid_mode" value={profGridMode} />

        <div className="grid cols-2 top-gap-sm">
          <GridPreview title="Grille generale (reference)" grid={professorReferenceGrid} currencyCode={currencyCode} />
          <GridPreview
            title="Grille professeur active"
            grid={profGridMode === "override" ? resolvedProfessorGrid : professorReferenceGrid}
            currencyCode={currencyCode}
          />
        </div>

        {profGridMode === "inherit" ? (
          <div className="row top-gap-sm">
            <button
              type="button"
              onClick={() => {
                setProfGridMode("override");
                if (profRules.length === 0) {
                  setProfRules(gridToEditableRules(professorReferenceGrid));
                }
              }}
            >
              Creer une surcouche professeur
            </button>
          </div>
        ) : (
          <>
            <RuleRowsEditor
              rows={profRules}
              currencyCode={currencyCode}
              onChange={setProfRules}
              onAdd={() => setProfRules((previous) => addRuleRow(previous))}
              onReset={() => setProfRules(gridToEditableRules(professorReferenceGrid))}
              resetLabel="Reinitialiser depuis la grille generale"
            />
            <div className="row top-gap-sm">
              <button
                type="button"
                className="danger"
                onClick={() => {
                  setProfGridMode("inherit");
                  setProfRules([]);
                }}
              >
                Supprimer la surcouche
              </button>
            </div>
          </>
        )}

        {profGridMode === "override"
          ? profRules.map((row) => (
              <div key={`prof-hidden-${row.id}`}>
                <input type="hidden" name="prof_grid_min" value={row.min} />
                <input type="hidden" name="prof_grid_max" value={row.max} />
                <input type="hidden" name="prof_grid_rate" value={normalizeMoneyInput(row.rate)} />
              </div>
            ))
          : null}

        <div className="prof-pay-simulation top-gap-sm">
          <strong>Simulation rapide</strong>
          <p className="muted">2 eleves: {formatMoney(resolveRate(profGridMode === "override" ? resolvedProfessorGrid : professorReferenceGrid, 2), currencyCode)}</p>
          <p className="muted">4 eleves: {formatMoney(resolveRate(profGridMode === "override" ? resolvedProfessorGrid : professorReferenceGrid, 4), currencyCode)}</p>
          <p className="muted">6 eleves: {formatMoney(resolveRate(profGridMode === "override" ? resolvedProfessorGrid : professorReferenceGrid, 6), currencyCode)}</p>
        </div>
      </article>

      <article className="card prof-pay-activities-card">
        <div className="row spread">
          <h3>3. Regles par activite</h3>
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
            <select value={activityFilter} onChange={(event) => setActivityFilter(event.target.value as "ALL" | "INHERITED" | "OVERRIDDEN")}>
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
              default_hourly_rate: activityDefaultRates[activity.course_type_id] ? normalizeMoneyInput(activityDefaultRates[activity.course_type_id]) : null,
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

            const inheritedProfessorGrid = profGridMode === "override" ? resolvedProfessorGrid : null;
            const activeGrid = mode === "SPECIFIC" ? specificGrid : mode === "PROFESSOR" ? (inheritedProfessorGrid ?? activity.general_grid) : activity.general_grid;
            const activeLabel =
              mode === "SPECIFIC"
                ? "Surcouche activite"
                : mode === "PROFESSOR"
                  ? "Herite de la grille professeur"
                  : "Herite de la grille generale";

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
                  <span className="badge">Regle active: {activeLabel}</span>
                </div>

                <label className="top-gap-sm">
                  Regle de paie
                  <select
                    value={mode}
                    onChange={(event) => {
                      const nextMode = event.target.value as "GENERAL" | "PROFESSOR" | "SPECIFIC";
                      setActivityModes((previous) => ({ ...previous, [activity.course_type_id]: nextMode }));
                      if (nextMode === "SPECIFIC" && (activityRules[activity.course_type_id] ?? []).length === 0) {
                        const seedGrid =
                          activity.general_grid ??
                          (profGridMode === "override" ? resolvedProfessorGrid : null) ?? {
                            default_hourly_rate: baseHourlyRate,
                            rules: [],
                          };
                        setActivityRules((previous) => ({
                          ...previous,
                          [activity.course_type_id]: gridToEditableRules(seedGrid),
                        }));
                        setActivityDefaultRates((previous) => ({
                          ...previous,
                          [activity.course_type_id]: seedGrid.default_hourly_rate ?? "",
                        }));
                      }
                    }}
                  >
                    <option value="GENERAL">Heriter de la grille generale</option>
                    <option value="PROFESSOR">Heriter de la grille professeur</option>
                    <option value="SPECIFIC">Definir une regle specifique</option>
                  </select>
                </label>

                {mode === "SPECIFIC" ? (
                  <>
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
                        const seed = activity.general_grid ?? (profGridMode === "override" ? resolvedProfessorGrid : null);
                        setActivityRules((previous) => ({
                          ...previous,
                          [activity.course_type_id]: gridToEditableRules(seed),
                        }));
                        setActivityDefaultRates((previous) => ({
                          ...previous,
                          [activity.course_type_id]: seed?.default_hourly_rate ?? "",
                        }));
                      }}
                      resetLabel="Reinitialiser depuis la grille heritee"
                    />

                    <div className="row">
                      <button
                        type="button"
                        className="ghost"
                        onClick={() => {
                          setActivityModes((previous) => ({ ...previous, [activity.course_type_id]: "PROFESSOR" }));
                          setActivityRules((previous) => ({ ...previous, [activity.course_type_id]: [] }));
                        }}
                      >
                        Supprimer la surcouche activite
                      </button>
                    </div>
                  </>
                ) : (
                  <div className="grid cols-2 top-gap-sm">
                    <GridPreview title="Grille generale" grid={activity.general_grid} currencyCode={currencyCode} />
                    <GridPreview
                      title="Regle appliquee"
                      grid={mode === "PROFESSOR" ? (inheritedProfessorGrid ?? activity.general_grid) : activity.general_grid}
                      currencyCode={currencyCode}
                    />
                  </div>
                )}

                <div className="prof-pay-simulation top-gap-sm">
                  <strong>Simulation rapide</strong>
                  <p className="muted">2 eleves: {formatMoney(resolveRate(activeGrid, 2), currencyCode)}</p>
                  <p className="muted">4 eleves: {formatMoney(resolveRate(activeGrid, 4), currencyCode)}</p>
                  <p className="muted">6 eleves: {formatMoney(resolveRate(activeGrid, 6), currencyCode)}</p>
                </div>

                {mode === "SPECIFIC" ? (
                  <>
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
                ) : null}
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
