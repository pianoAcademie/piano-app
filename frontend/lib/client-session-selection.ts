import type { ClientSessionReservationMemberOptionOut, SessionOut } from "./types";

export function preferredReservationMemberId(
  members: ClientSessionReservationMemberOptionOut[],
  requestedMemberId: string,
): string {
  const requested = requestedMemberId.trim();
  if (requested && members.some((member) => member.member_id === requested)) {
    return requested;
  }
  if (members.length === 1) {
    return members[0]?.member_id ?? "";
  }

  const eligibleMembers = members.filter(
    (member) => String(member.action_code || "").trim().toUpperCase() !== "UNAVAILABLE",
  );
  return eligibleMembers.length === 1 ? eligibleMembers[0]?.member_id ?? "" : "";
}

export function isChildOnlyBookingSession(session: SessionOut | null): boolean {
  return Boolean(session?.child_bookings_enabled && !session?.adult_bookings_enabled);
}
