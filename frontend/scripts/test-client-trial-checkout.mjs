import assert from "node:assert/strict";
import test from "node:test";
import { clientSessionCheckoutAccess } from "../lib/client-session-selection.ts";

const session = {
  status: "SCHEDULED", online_booking_enabled: true,
  child_bookings_enabled: true, adult_bookings_enabled: true,
  child_trial_bookings_enabled: true, adult_trial_bookings_enabled: true,
  adult_capacity_max: 2, adult_booked_count: 0, capacity_max: 6, booked_count: 2,
  external_booking_price_ttc: null,
  course_type: { name: "Cours collectif enfants en présentiel", trial_course_price_ttc: "20.00" },
};
const context = {
  hasBooking: false, paymentPending: false, renewalRequired: false,
  eligibleByPlan: false, sessionIsPastOrStarted: false,
};
const access = (changes = {}, kind = "ADULT", state = {}) => clientSessionCheckoutAccess(
  { ...session, ...changes }, kind, { ...context, ...state },
);

test("adult can reach paid trial checkout on an enabled child collective without a plan or unit price", () => {
  const result = access();
  assert.equal(result.canCheckout, true);
  assert.equal(result.hasDirectPayment, false);
  assert.equal(result.hasTrialPurchaseOption, true);
  assert.equal(result.requiresPayment, true);
});
test("a child trial flag does not authorize an adult trial", () => {
  assert.equal(access({ adult_trial_bookings_enabled: false }).canCheckout, false);
  assert.equal(access({ adult_trial_bookings_enabled: false }, "CHILD").canCheckout, true);
});
test("adult participation must remain explicitly enabled", () => {
  assert.equal(access({ adult_bookings_enabled: false }).canCheckout, false);
});
test("adult quota prevents checkout even when total seats remain", () => {
  const full = { adult_booked_count: 2 };
  assert.equal(access(full).canCheckout, false);
  assert.equal(access(full).adultQuotaFull, true);
  assert.equal(access(full, "CHILD").canCheckout, true);
});
test("global capacity prevents both adult and child checkout", () => {
  for (const kind of ["ADULT", "CHILD"]) assert.equal(access({ booked_count: 6 }, kind).canCheckout, false);
});
test("compatible subscription keeps credit booking without an extra trial charge", () => {
  const result = access({}, "ADULT", { eligibleByPlan: true });
  assert.equal(result.canCheckout, true);
  assert.equal(result.requiresPayment, false);
});
test("unit payment still works when adult trials are disabled", () => {
  const result = access({ adult_trial_bookings_enabled: false, external_booking_price_ttc: "38.00" });
  assert.equal(result.canCheckout, true);
  assert.equal(result.requiresPayment, true);
});
test("missing or invalid trial price cannot create a checkout option", () => {
  for (const price of [null, undefined, "", "0", "invalid", "Infinity"])
    assert.equal(access({ course_type: { trial_course_price_ttc: price } }).canCheckout, false);
});
test("past, cancelled and closed sessions remain unavailable", () => {
  assert.equal(access({ status: "CANCELLED" }).canCheckout, false);
  assert.equal(access({ online_booking_enabled: false }).canCheckout, false);
  assert.equal(access({}, "ADULT", { sessionIsPastOrStarted: true }).canCheckout, false);
});
test("existing bookings and renewal constraints remain respected", () => {
  assert.equal(access({}, "ADULT", { hasBooking: true }).canCheckout, false);
  assert.equal(access({}, "ADULT", { renewalRequired: true }).canCheckout, false);
  assert.equal(access({}, "ADULT", { hasBooking: true, paymentPending: true }).canCheckout, true);
});
