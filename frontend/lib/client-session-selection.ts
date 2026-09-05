import type { ClientSessionReservationMemberOptionOut, SessionOut } from "./types";

export function preferredReservationMemberId(
  members: ClientSessionReservationMemberOptionOut[],
  requestedMemberId: string,
): string {
  const requested = requestedMemberId.trim();
  const eligibleMembers = members.filter(
    (member) => String(member.action_code || "").trim().toUpperCase() !== "UNAVAILABLE",
  );
  const requestedMember = requested
    ? members.find((member) => member.member_id === requested)
    : null;
  if (
    requestedMember
    && String(requestedMember.action_code || "").trim().toUpperCase() !== "UNAVAILABLE"
  ) {
    return requestedMember.member_id;
  }
  if (members.length === 1) {
    return members[0]?.member_id ?? "";
  }
  return eligibleMembers.length === 1 ? eligibleMembers[0]?.member_id ?? "" : "";
}

export function eligibleReservationMembers(
  members: ClientSessionReservationMemberOptionOut[],
): ClientSessionReservationMemberOptionOut[] {
  return members.filter(
    (member) => String(member.action_code || "").trim().toUpperCase() !== "UNAVAILABLE",
  );
}

export function isChildOnlyBookingSession(session: SessionOut | null): boolean {
  return Boolean(session?.child_bookings_enabled && !session?.adult_bookings_enabled);
}

// Calendar availability is an invitation to checkout. The reservation-options
// endpoint still decides member eligibility, including the single-trial rule.
export function clientSessionCheckoutAccess(
  session: SessionOut,
  memberKind: string,
  context: {
    hasBooking: boolean;
    paymentPending: boolean;
    renewalRequired: boolean;
    eligibleByPlan: boolean;
    sessionIsPastOrStarted: boolean;
  },
) {
  const participantAllowed = memberKind === "CHILD" ? session.child_bookings_enabled : session.adult_bookings_enabled;
  const trialAllowed = memberKind === "CHILD" ? session.child_trial_bookings_enabled : session.adult_trial_bookings_enabled;
  const trialPrice = Number(session.course_type.trial_course_price_ttc ?? "0");
  const hasTrialPurchaseOption = Boolean(trialAllowed) && Number.isFinite(trialPrice) && trialPrice > 0;
  const hasDirectPayment = Number(session.external_booking_price_ttc ?? "0") > 0;
  const adultQuotaFull = memberKind !== "CHILD"
    && session.adult_capacity_max !== null
    && session.adult_booked_count >= session.adult_capacity_max;
  const isFull = session.booked_count >= session.capacity_max || adultQuotaFull;
  const requiresPayment = !context.eligibleByPlan && (hasDirectPayment || hasTrialPurchaseOption);
  const canCheckout =
    String(session.status).trim().toUpperCase() === "SCHEDULED"
    && session.online_booking_enabled
    && participantAllowed
    && !context.sessionIsPastOrStarted
    && !isFull
    && (context.paymentPending || (
      !context.hasBooking && !context.renewalRequired
      && (context.eligibleByPlan || hasDirectPayment || hasTrialPurchaseOption)
    ));
  return { participantAllowed, adultQuotaFull, isFull, hasDirectPayment, hasTrialPurchaseOption, requiresPayment, canCheckout };
}
