type RecurringRow = {
  session: { recurrence_group_id?: string | null };
  local: { date: string };
};

export function selectCohesiveRecurringRows<T extends RecurringRow>(rows: T[]): T[] {
  const bySeries = new Map<string, T[]>();
  for (const row of rows) {
    const seriesKey = String(row.session.recurrence_group_id || "").trim();
    if (!seriesKey) continue;
    const group = bySeries.get(seriesKey) ?? [];
    group.push(row);
    bySeries.set(seriesKey, group);
  }
  if (bySeries.size < 2) return rows;

  const ownersByDate = new Map<string, Set<string>>();
  for (const [seriesKey, group] of bySeries.entries()) {
    for (const row of group) {
      const owners = ownersByDate.get(row.local.date) ?? new Set<string>();
      owners.add(seriesKey);
      ownersByDate.set(row.local.date, owners);
    }
  }
  // Disjoint recurrence ids can be legitimate fragments of one annual series.
  // Overlap means that several competing versions of the same slot coexist.
  if (![...ownersByDate.values()].some((owners) => owners.size > 1)) return rows;

  const ranked = [...bySeries.entries()].sort((left, right) => {
    const leftRows = [...left[1]].sort((a, b) => a.local.date.localeCompare(b.local.date));
    const rightRows = [...right[1]].sort((a, b) => a.local.date.localeCompare(b.local.date));
    const byLatestEnd = rightRows.at(-1)!.local.date.localeCompare(leftRows.at(-1)!.local.date);
    if (byLatestEnd !== 0) return byLatestEnd;
    const byEarliestStart = leftRows[0].local.date.localeCompare(rightRows[0].local.date);
    if (byEarliestStart !== 0) return byEarliestStart;
    return rightRows.length - leftRows.length;
  });
  const selectedKey = ranked[0]?.[0];
  return selectedKey
    ? rows.filter((row) => String(row.session.recurrence_group_id || "").trim() === selectedKey)
    : rows;
}
