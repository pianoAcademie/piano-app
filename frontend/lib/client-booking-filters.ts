import type { LocationOut, SessionOut } from "./types";

export type ClientBookingCategory = "PIANO" | "REHEARSAL_STUDIO" | "ONLINE_SOLFEGE";
export type ClientStudentSite = "PARIS" | "BAR_LE_DUC" | "ONLINE";

const PARIS_LOCATION_CODES = new Set(["ASSAS", "DULONG", "POMPE", "RICHELIEU", "SCHEFFER"]);

function normalizeText(value: string | null | undefined): string {
  return (value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function parseClientBookingCategory(value: string): ClientBookingCategory {
  const normalized = value.trim().toUpperCase();
  if (normalized === "REHEARSAL_STUDIO" || normalized === "ONLINE_SOLFEGE") {
    return normalized;
  }
  return "PIANO";
}

export function clientBookingCategoryForSession(session: SessionOut): ClientBookingCategory {
  const text = normalizeText(
    [session.title, session.course_type.name, session.course_type.code].filter(Boolean).join(" "),
  );
  if (/\b(studio|repetition)\b/.test(text)) {
    return "REHEARSAL_STUDIO";
  }
  if (session.location.is_online && /\b(solfege|formation musicale|theorie musicale)\b/.test(text)) {
    return "ONLINE_SOLFEGE";
  }
  return "PIANO";
}

export function clientStudentSiteForLocation(
  location: Pick<LocationOut, "code" | "name" | "city" | "is_online">,
): ClientStudentSite | null {
  if (location.is_online) {
    return "ONLINE";
  }
  const code = location.code.trim().toUpperCase();
  const label = normalizeText(`${location.name} ${location.city || ""}`);
  if (code === "BAR_LE_DUC" || label.includes("bar le duc")) {
    return "BAR_LE_DUC";
  }
  if (PARIS_LOCATION_CODES.has(code) || normalizeText(location.city) === "paris") {
    return "PARIS";
  }
  return null;
}

export function locationAllowedForClientSites(
  location: Pick<LocationOut, "code" | "name" | "city" | "is_online">,
  sites: Iterable<string | null | undefined>,
): boolean {
  const normalizedSites = new Set(
    Array.from(sites)
      .map((site) => String(site || "").trim().toUpperCase())
      .filter((site): site is ClientStudentSite =>
        site === "PARIS" || site === "BAR_LE_DUC" || site === "ONLINE",
      ),
  );
  if (normalizedSites.size === 0) {
    return true;
  }
  const locationSite = clientStudentSiteForLocation(location);
  if (locationSite === "ONLINE") {
    return true;
  }
  return locationSite !== null && normalizedSites.has(locationSite);
}

export function parseFavoriteLocationIds(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}
