"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import type {
  AdminActivityOut,
  AdminProfessorDefaultGridLineOut,
  AdminProfessorPayGridPeriodOut,
} from "../lib/types";

type GridRule = {
  min_students: number;
  max_students: number | null;
  hourly_rate: string;
};

type EditableRule = {
  id: string;
  min: string;
  max: string;
  rate: string;
};

type Props = {
  activities: AdminActivityOut[];
  periods: AdminProfessorPayGridPeriodOut[];
  selectedPeriod: AdminProfessorPayGridPeriodOut | null;
  selectedLines: AdminProfessorDefaultGridLineOut[];
  selectedPeriodId: string | null;
  createPeriodAction: (formData: FormData) => Promise<void>;
  updatePeriodAction: (formData: FormData) => Promise<void>;
  archivePeriodAction: (formData: FormData) => Promise<void>;
  updatePeriodRulesAction: (formData: FormData) => Promise<void>;
  defaultCurrency: string;
  sectionPath?: string;
};

function formatPeriodLabel(period: AdminProfessorPayGridPeriodOut): string {
  return `${period.start_date} -> ${period.end_date ?? "en cours"}`;
}

function periodBadgeLabel(period: AdminProfessorPayGridPeriodOut): string {
  if (period.is_active) {
    return "Active";
  }
  if (period.is_future) {
    return "Future";
  }
  return "Archivee";
}

function normalizeMoney(value: string): string {
  return value.replace(",", ".").trim();
}

function lineModeLabel(mode: string): string {
  const normalized = mode.toUpperCase();
  if (normalized === "EN_LIGNE") {
    return "En ligne";
  }
  if (normalized === "PRESENTIEL") {
    return "Presentiel";
  }
  return "Autre";
}

function toEditableRules(rules: GridRule[]): EditableRule[] {
  return rules.map((rule, index) => ({
    id: `${index}-${rule.min_students}-${rule.max_students ?? "open"}`,
    min: String(rule.min_students),
    max: rule.max_students === null ? "" : String(rule.max_students),
    rate: String(rule.hourly_rate),
  }));
}

function addRuleRow(previous: EditableRule[]): EditableRule[] {
  const last = previous[previous.length - 1];
  if (!last) {
    return [{ id: `${Date.now()}-${Math.random()}`, min: "0", max: "", rate: "" }];
  }
  const maxValue = Number.parseInt(last.max, 10);
  const minValue = Number.parseInt(last.min, 10);
  const nextMin = Number.isFinite(maxValue) ? maxValue + 1 : (Number.isFinite(minValue) ? minValue + 1 : 0);
  return [...previous, { id: `${Date.now()}-${Math.random()}`, min: String(nextMin), max: "", rate: "" }];
}

export default function AdminProfessorDefaultGridManager({
  activities,
  periods,
  selectedPeriod,
  selectedLines,
  selectedPeriodId,
  createPeriodAction,
  updatePeriodAction,
  archivePeriodAction,
  updatePeriodRulesAction,
  defaultCurrency,
  sectionPath = "/admin/config?section=params-professor-default-grid",
}: Props): JSX.Element {
  const buildSectionHref = (params: Record<string, string> = {}): string => {
    const query = new URLSearchParams();
    const separator = sectionPath.includes("?") ? "&" : "?";
    const hasQuery = sectionPath.includes("?");
    for (const [key, value] of Object.entries(params)) {
      if (!value) {
        continue;
      }
      query.set(key, value);
    }
    if ([...query.keys()].length === 0) {
      return sectionPath;
    }
    return `${sectionPath}${hasQuery ? "&" : separator}${query.toString()}`;
  };

  const sortedActivities = useMemo(
    () => [...activities].filter((row) => row.active).sort((a, b) => a.name.localeCompare(b.name, "fr")),
    [activities],
  );
  const lineByCourseTypeId = useMemo(
    () => new Map(selectedLines.map((line) => [line.course_type_id, line])),
    [selectedLines],
  );

  const [search, setSearch] = useState("");
  const [modeFilter, setModeFilter] = useState<"ALL" | "ONLINE" | "ONSITE">("ALL");
  const [currencyCode, setCurrencyCode] = useState(defaultCurrency || "EUR");
  const [defaultRates, setDefaultRates] = useState<Record<string, string>>(
    Object.fromEntries(
      sortedActivities.map((activity) => [activity.id, lineByCourseTypeId.get(activity.id)?.default_hourly_rate ?? ""]),
    ),
  );
  const [rulesByActivity, setRulesByActivity] = useState<Record<string, EditableRule[]>>(
    Object.fromEntries(
      sortedActivities.map((activity) => {
        const line = lineByCourseTypeId.get(activity.id);
        const rules = (line?.rules ?? []).map((rule) => ({
          min_students: rule.min_students,
          max_students: rule.max_students,
          hourly_rate: rule.hourly_rate,
        }));
        return [activity.id, toEditableRules(rules)];
      }),
    ),
  );

  const visibleActivities = useMemo(() => {
    const query = search.trim().toLowerCase();
    return sortedActivities.filter((activity) => {
      if (modeFilter === "ONLINE" && activity.mode !== "ONLINE") {
        return false;
      }
      if (modeFilter === "ONSITE" && activity.mode !== "ONSITE") {
        return false;
      }
      if (!query) {
        return true;
      }
      return activity.name.toLowerCase().includes(query);
    });
  }, [modeFilter, search, sortedActivities]);

  const activeCount = useMemo(
    () => sortedActivities.filter((activity) => {
      const hasRate = Boolean((defaultRates[activity.id] ?? "").trim());
      const hasRules = (rulesByActivity[activity.id] ?? []).some((rule) => rule.min || rule.max || rule.rate);
      return hasRate || hasRules;
    }).length,
    [defaultRates, rulesByActivity, sortedActivities],
  );

  return (
    <section className="card">
      <div className="row spread">
        <div>
          <h3>Grille generale de remuneration des professeurs</h3>
          <p className="muted">Definissez les taux horaires par activite, par nombre d eleves et par periode de validite.</p>
        </div>
        <span className="badge">{periods.length} periode(s)</span>
      </div>

      <article className="item top-gap-sm">
        <strong>Creer une nouvelle periode</strong>
        <form action={createPeriodAction} className="grid cols-4 top-gap-sm">
          <input type="hidden" name="return_to" value={sectionPath} />
          <label>
            Date debut
            <input type="date" name="start_date" required />
          </label>
          <label>
            Date fin (optionnel)
            <input type="date" name="end_date" />
          </label>
          <label>
            Dupliquer depuis
            <select name="clone_from_period_id" defaultValue="">
              <option value="">Ne pas dupliquer</option>
              {periods.map((period) => (
                <option key={`clone-${period.id}`} value={period.id}>
                  {formatPeriodLabel(period)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Notes
            <input type="text" name="notes" maxLength={2000} />
          </label>
          <div className="row span-4">
            <button type="submit">Creer la periode</button>
          </div>
        </form>
      </article>

      <article className="item top-gap-sm">
        <strong>Periodes disponibles</strong>
        <div className="list top-gap-sm">
          {periods.map((period) => {
            const isSelected = selectedPeriodId === period.id;
            return (
              <article key={period.id} className={`item ${isSelected ? "active" : ""}`}>
                <div className="row spread">
                  <div>
                    <strong>{formatPeriodLabel(period)}</strong>
                    <p className="muted">{period.notes ?? "Sans note"}</p>
                  </div>
                  <div className="row">
                    <span className="badge">{periodBadgeLabel(period)}</span>
                    <span className="badge">{period.rules_count} regle(s)</span>
                    <Link className="mode-link" href={buildSectionHref({ grid_period: period.id })}>
                      Ouvrir
                    </Link>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </article>

      {selectedPeriod ? (
        <>
          <article className="item top-gap-sm">
            <div className="row spread">
              <strong>Periode selectionnee</strong>
              <span className="badge">{periodBadgeLabel(selectedPeriod)}</span>
            </div>
            <form action={updatePeriodAction} className="grid cols-4 top-gap-sm">
              <input type="hidden" name="period_id" value={selectedPeriod.id} />
              <input type="hidden" name="return_to" value={buildSectionHref({ grid_period: selectedPeriod.id })} />
              <label>
                Date debut
                <input type="date" name="start_date" defaultValue={selectedPeriod.start_date} required />
              </label>
              <label>
                Date fin
                <input type="date" name="end_date" defaultValue={selectedPeriod.end_date ?? ""} />
              </label>
              <label>
                Statut
                <select name="status" defaultValue={selectedPeriod.status}>
                  <option value="ACTIVE">ACTIVE</option>
                  <option value="FUTURE">FUTURE</option>
                  <option value="ARCHIVED">ARCHIVED</option>
                </select>
              </label>
              <label>
                Notes
                <input type="text" name="notes" maxLength={2000} defaultValue={selectedPeriod.notes ?? ""} />
              </label>
              <div className="row span-4">
                <button type="submit">Mettre a jour la periode</button>
              </div>
            </form>
            {!selectedPeriod.is_archived ? (
              <form action={archivePeriodAction} className="top-gap-sm">
                <input type="hidden" name="period_id" value={selectedPeriod.id} />
                <input type="hidden" name="return_to" value={buildSectionHref({ grid_period: selectedPeriod.id })} />
                <button type="submit" className="danger">Archiver la periode</button>
              </form>
            ) : null}
          </article>

          <article className="item top-gap-sm">
            <div className="row spread">
              <strong>Activites de la periode</strong>
              <span className="badge">{activeCount} activite(s) configuree(s)</span>
            </div>

            <form action={updatePeriodRulesAction} className="grid top-gap-sm">
              <input type="hidden" name="period_id" value={selectedPeriod.id} />
              <input type="hidden" name="return_to" value={buildSectionHref({ grid_period: selectedPeriod.id })} />
              <input type="hidden" name="default_grid_ui_version" value="2" />
              <div className="row">
                <label>
                  Devise
                  <select name="currency_code" value={currencyCode} onChange={(event) => setCurrencyCode(event.target.value)}>
                    <option value="EUR">EUR</option>
                    <option value="USD">USD</option>
                  </select>
                </label>
                <label className="prof-pay-search">
                  Recherche activite
                  <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Nom activite" />
                </label>
                <label>
                  Filtre mode
                  <select value={modeFilter} onChange={(event) => setModeFilter(event.target.value as "ALL" | "ONLINE" | "ONSITE") }>
                    <option value="ALL">Tous modes</option>
                    <option value="ONSITE">Presentiel</option>
                    <option value="ONLINE">En ligne</option>
                  </select>
                </label>
              </div>

              <div className="prof-pay-activity-list">
                {visibleActivities.map((activity) => {
                  const rules = rulesByActivity[activity.id] ?? [];
                  return (
                    <article key={`period-activity-${activity.id}`} className="item prof-pay-activity-card">
                      <input type="hidden" name="line_course_type_id" value={activity.id} />

                      <div className="row spread">
                        <div>
                          <strong>{activity.name}</strong>
                          <p className="muted">
                            {lineModeLabel(activity.mode)} | Duree ref: {activity.duration_minutes ?? "-"} min
                          </p>
                        </div>
                        <span className="badge">{(rules.length > 0 || (defaultRates[activity.id] ?? "").trim()) ? "Configuree" : "Vide"}</span>
                      </div>

                      <label>
                        Taux de base (fallback)
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={defaultRates[activity.id] ?? ""}
                          onChange={(event) =>
                            setDefaultRates((previous) => ({
                              ...previous,
                              [activity.id]: event.target.value,
                            }))
                          }
                        />
                      </label>

                      <input type="hidden" name={`line_default_rate_${activity.id}`} value={normalizeMoney(defaultRates[activity.id] ?? "")} />

                      <div className="table-wrap top-gap-sm">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Min eleves</th>
                              <th>Max eleves</th>
                              <th>Taux horaire</th>
                              <th>Action</th>
                            </tr>
                          </thead>
                          <tbody>
                            {rules.length === 0 ? (
                              <tr>
                                <td colSpan={4} className="muted">Aucune tranche definie</td>
                              </tr>
                            ) : null}
                            {rules.map((rule) => (
                              <tr key={rule.id}>
                                <td>
                                  <input
                                    type="number"
                                    min={0}
                                    step={1}
                                    value={rule.min}
                                    onChange={(event) =>
                                      setRulesByActivity((previous) => ({
                                        ...previous,
                                        [activity.id]: (previous[activity.id] ?? []).map((candidate) =>
                                          candidate.id === rule.id ? { ...candidate, min: event.target.value } : candidate,
                                        ),
                                      }))
                                    }
                                  />
                                </td>
                                <td>
                                  <input
                                    type="number"
                                    min={0}
                                    step={1}
                                    value={rule.max}
                                    placeholder="+"
                                    onChange={(event) =>
                                      setRulesByActivity((previous) => ({
                                        ...previous,
                                        [activity.id]: (previous[activity.id] ?? []).map((candidate) =>
                                          candidate.id === rule.id ? { ...candidate, max: event.target.value } : candidate,
                                        ),
                                      }))
                                    }
                                  />
                                </td>
                                <td>
                                  <input
                                    type="number"
                                    min={0}
                                    step="0.01"
                                    value={rule.rate}
                                    onChange={(event) =>
                                      setRulesByActivity((previous) => ({
                                        ...previous,
                                        [activity.id]: (previous[activity.id] ?? []).map((candidate) =>
                                          candidate.id === rule.id ? { ...candidate, rate: event.target.value } : candidate,
                                        ),
                                      }))
                                    }
                                  />
                                </td>
                                <td>
                                  <button
                                    type="button"
                                    className="ghost"
                                    onClick={() =>
                                      setRulesByActivity((previous) => ({
                                        ...previous,
                                        [activity.id]: (previous[activity.id] ?? []).filter((candidate) => candidate.id !== rule.id),
                                      }))
                                    }
                                  >
                                    Supprimer
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>

                      <div className="row top-gap-sm">
                        <button
                          type="button"
                          className="ghost"
                          onClick={() =>
                            setRulesByActivity((previous) => ({
                              ...previous,
                              [activity.id]: addRuleRow(previous[activity.id] ?? []),
                            }))
                          }
                        >
                          Ajouter une tranche
                        </button>
                        <button
                          type="button"
                          className="ghost"
                          onClick={() =>
                            setRulesByActivity((previous) => ({
                              ...previous,
                              [activity.id]: [],
                            }))
                          }
                        >
                          Vider les tranches
                        </button>
                      </div>

                      {(rulesByActivity[activity.id] ?? []).map((rule) => (
                        <div key={`hidden-rule-${activity.id}-${rule.id}`}>
                          <input type="hidden" name={`line_rule_min_${activity.id}`} value={rule.min} />
                          <input type="hidden" name={`line_rule_max_${activity.id}`} value={rule.max} />
                          <input type="hidden" name={`line_rule_rate_${activity.id}`} value={normalizeMoney(rule.rate)} />
                        </div>
                      ))}
                    </article>
                  );
                })}
                {visibleActivities.length === 0 ? <p className="muted">Aucune activite ne correspond aux filtres.</p> : null}
              </div>

              <div className="row">
                <button type="submit">Enregistrer la grille de la periode</button>
              </div>
            </form>
          </article>
        </>
      ) : (
        <article className="item top-gap-sm">
          <p className="muted">Selectionnez une periode pour modifier sa grille par activite.</p>
        </article>
      )}
    </section>
  );
}
