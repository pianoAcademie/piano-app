"use client";

import { useMemo, useState } from "react";

export type InvoiceLineSelectionRow = {
  key: string;
  participantId: string | null;
  participantLabel: string;
  dateLabel: string;
  sourceLabel: string;
  label: string;
  reference: string | null;
  statusLabel: string;
  totalLabel: string;
  totalInclVat: string;
  currency: string;
};

type InvoiceLineSelectionLabels = {
  quickSelection: string;
  quickSelectionHelp: string;
  selectAll: string;
  deselectAll: string;
  selectOnly: string;
  selectedCount: string;
  lineSingular: string;
  linePlural: string;
  include: string;
  participant: string;
  date: string;
  type: string;
  description: string;
  status: string;
  total: string;
};

type InvoiceLineSelectionProps = {
  rows: InvoiceLineSelectionRow[];
  initialSelectedKeys: string[];
  labels: InvoiceLineSelectionLabels;
  locale: string;
};

type ParticipantGroup = {
  id: string;
  label: string;
  rowKeys: string[];
};

function selectionTotal(rows: InvoiceLineSelectionRow[], selectedKeys: Set<string>, locale: string): string {
  const totals = new Map<string, number>();
  for (const row of rows) {
    if (!selectedKeys.has(row.key)) {
      continue;
    }
    const amount = Number(row.totalInclVat || "0");
    if (!Number.isFinite(amount)) {
      continue;
    }
    const currency = row.currency || "EUR";
    totals.set(currency, (totals.get(currency) ?? 0) + amount);
  }
  return [...totals.entries()]
    .map(([currency, amount]) =>
      new Intl.NumberFormat(locale, { style: "currency", currency }).format(amount),
    )
    .join(" | ");
}

export default function InvoiceLineSelection({
  rows,
  initialSelectedKeys,
  labels,
  locale,
}: InvoiceLineSelectionProps): JSX.Element {
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(() => {
    const availableKeys = new Set(rows.map((row) => row.key));
    return new Set(initialSelectedKeys.filter((key) => availableKeys.has(key)));
  });
  const groups = useMemo<ParticipantGroup[]>(() => {
    const grouped = new Map<string, ParticipantGroup>();
    for (const row of rows) {
      const groupId = row.participantId ? `participant:${row.participantId}` : "participant:unassigned";
      const existing = grouped.get(groupId);
      if (existing) {
        existing.rowKeys.push(row.key);
      } else {
        grouped.set(groupId, {
          id: groupId,
          label: row.participantLabel,
          rowKeys: [row.key],
        });
      }
    }
    return [...grouped.values()].sort((left, right) => left.label.localeCompare(right.label, locale));
  }, [locale, rows]);

  const selectedTotal = selectionTotal(rows, selectedKeys, locale);

  const replaceSelection = (keys: Iterable<string>) => {
    setSelectedKeys(new Set(keys));
  };

  const toggleGroup = (group: ParticipantGroup) => {
    const allSelected = group.rowKeys.every((key) => selectedKeys.has(key));
    const next = new Set(selectedKeys);
    for (const key of group.rowKeys) {
      if (allSelected) {
        next.delete(key);
      } else {
        next.add(key);
      }
    }
    setSelectedKeys(next);
  };

  return (
    <>
      <section className="invoice-participant-selector" aria-label={labels.quickSelection}>
        <div className="invoice-participant-selector-heading">
          <div>
            <strong>{labels.quickSelection}</strong>
            <small>{labels.quickSelectionHelp}</small>
          </div>
          <div className="invoice-participant-global-actions">
            <button type="button" className="mode-link" onClick={() => replaceSelection(rows.map((row) => row.key))}>
              {labels.selectAll}
            </button>
            <button type="button" className="mode-link" onClick={() => replaceSelection([])}>
              {labels.deselectAll}
            </button>
          </div>
        </div>
        <div className="invoice-participant-groups">
          {groups.map((group) => {
            const selectedCount = group.rowKeys.filter((key) => selectedKeys.has(key)).length;
            const allSelected = selectedCount === group.rowKeys.length;
            const lineLabel = group.rowKeys.length === 1 ? labels.lineSingular : labels.linePlural;
            return (
              <article key={group.id} className={allSelected ? "is-selected" : ""}>
                <button
                  type="button"
                  className="invoice-participant-toggle"
                  onClick={() => toggleGroup(group)}
                  aria-pressed={allSelected}
                >
                  <span className="invoice-participant-check" aria-hidden="true">{allSelected ? "✓" : selectedCount > 0 ? "−" : ""}</span>
                  <span>
                    <strong>{group.label}</strong>
                    <small>{selectedCount}/{group.rowKeys.length} {lineLabel}</small>
                  </span>
                </button>
                <button type="button" className="mode-link" onClick={() => replaceSelection(group.rowKeys)}>
                  {labels.selectOnly}
                </button>
              </article>
            );
          })}
        </div>
      </section>

      <div className="invoice-selection-live-summary" aria-live="polite">
        <strong>{labels.selectedCount.replace("{selected}", String(selectedKeys.size)).replace("{total}", String(rows.length))}</strong>
        {selectedTotal ? <span>{selectedTotal}</span> : null}
      </div>

      <div className="table-wrap invoice-line-selection">
        <table className="data-table">
          <thead>
            <tr>
              <th>{labels.include}</th>
              <th>{labels.participant}</th>
              <th>{labels.date}</th>
              <th>{labels.type}</th>
              <th>{labels.description}</th>
              <th>{labels.status}</th>
              <th>{labels.total}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`invoice-candidate-${row.key}`}>
                <td>
                  <input
                    type="checkbox"
                    name="selected_payment_keys"
                    value={row.key}
                    checked={selectedKeys.has(row.key)}
                    onChange={(event) => {
                      const next = new Set(selectedKeys);
                      if (event.currentTarget.checked) {
                        next.add(row.key);
                      } else {
                        next.delete(row.key);
                      }
                      setSelectedKeys(next);
                    }}
                    aria-label={`${labels.include} ${row.label}`}
                  />
                </td>
                <td><strong>{row.participantLabel}</strong></td>
                <td>{row.dateLabel}</td>
                <td>{row.sourceLabel}</td>
                <td>
                  <div className="stack-xs">
                    <span>{row.label}</span>
                    <small className="muted">{row.reference ?? "-"}</small>
                  </div>
                </td>
                <td>{row.statusLabel}</td>
                <td>{row.totalLabel}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
