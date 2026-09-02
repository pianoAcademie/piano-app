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
