import assert from "node:assert/strict";
import test from "node:test";

import {
  clientBookingCategoryForSession,
  clientStudentSiteForLocation,
  locationAllowedForClientSites,
  parseFavoriteLocationIds,
} from "../lib/client-booking-filters.ts";
import {
  isChildOnlyBookingSession,
  preferredReservationMemberId,
} from "../lib/client-session-selection.ts";

const paris = { id: "paris", code: "RICHELIEU", name: "Rue de Richelieu", city: "Paris", is_online: false };
const barLeDuc = { id: "bld", code: "BAR_LE_DUC", name: "Bar-le-Duc", city: "Bar-le-Duc", is_online: false };
const online = { id: "online", code: "ONLINE", name: "Online", city: null, is_online: true };

function session({ title, courseName, courseCode, location }) {
  return {
    title,
    course_type: { id: "course", name: courseName, code: courseCode },
    location,
  };
}

test("Paris clients never receive Bar-le-Duc physical locations", () => {
  assert.equal(locationAllowedForClientSites(paris, ["PARIS"]), true);
  assert.equal(locationAllowedForClientSites(barLeDuc, ["PARIS"]), false);
  assert.equal(locationAllowedForClientSites(online, ["PARIS"]), true);
});

test("Bar-le-Duc clients receive their site and online courses", () => {
  assert.equal(locationAllowedForClientSites(paris, ["BAR_LE_DUC"]), false);
  assert.equal(locationAllowedForClientSites(barLeDuc, ["BAR_LE_DUC"]), true);
  assert.equal(locationAllowedForClientSites(online, ["BAR_LE_DUC"]), true);
  assert.equal(clientStudentSiteForLocation(barLeDuc), "BAR_LE_DUC");
});

test("booking categories separate piano, studio and online music theory", () => {
  assert.equal(
    clientBookingCategoryForSession(session({
      title: "Cours collectifs adultes",
      courseName: "Cours de piano collectif",
      courseCode: "PIANO_GROUP",
      location: paris,
    })),
    "PIANO",
  );
  assert.equal(
    clientBookingCategoryForSession(session({
      title: "Réservation studio de répétition",
      courseName: "Studio",
      courseCode: "STUDIO",
      location: paris,
    })),
    "REHEARSAL_STUDIO",
  );
  assert.equal(
    clientBookingCategoryForSession(session({
      title: "Solfège en ligne",
      courseName: "Formation musicale",
      courseCode: "SOLFEGE_ONLINE",
      location: online,
    })),
    "ONLINE_SOLFEGE",
  );
});

test("favorite location ids are trimmed and deduplicated", () => {
  assert.deepEqual(parseFavoriteLocationIds("paris, assas,paris,,"), ["paris", "assas"]);
});

test("child-only checkout selects the sole eligible family member", () => {
  const members = [
    { member_id: "parent", action_code: "UNAVAILABLE" },
    { member_id: "child", action_code: "BUY_FORMULA" },
  ];

  assert.equal(preferredReservationMemberId(members, ""), "child");
  assert.equal(preferredReservationMemberId(members, "parent"), "parent");
});

test("child-only sessions preserve child account creation context", () => {
  assert.equal(
    isChildOnlyBookingSession({ child_bookings_enabled: true, adult_bookings_enabled: false }),
    true,
  );
  assert.equal(
    isChildOnlyBookingSession({ child_bookings_enabled: true, adult_bookings_enabled: true }),
    false,
  );
});
