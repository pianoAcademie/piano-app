"use client";

import { useState } from "react";

type SessionVisibilityFieldsProps = {
  initialIsPrivate: boolean;
  initialAllowOnlineBooking: boolean;
};

export default function SessionVisibilityFields({
  initialIsPrivate,
  initialAllowOnlineBooking,
}: SessionVisibilityFieldsProps): JSX.Element {
  const [isPrivate, setIsPrivate] = useState<boolean>(initialIsPrivate);
  const [allowOnlineBooking, setAllowOnlineBooking] = useState<boolean>(
    initialIsPrivate ? false : initialAllowOnlineBooking,
  );

  return (
    <>
      <label className="checkline create-session-toggle">
        <input
          type="radio"
          name="session_visibility"
          value="PRIVATE"
          checked={isPrivate}
          onChange={() => {
            setIsPrivate(true);
            setAllowOnlineBooking(false);
          }}
        />
        Creneau prive
      </label>

      <label className="checkline create-session-toggle">
        <input
          type="radio"
          name="session_visibility"
          value="PUBLIC"
          checked={!isPrivate}
          onChange={() => setIsPrivate(false)}
        />
        Creneau public
      </label>

      <label className="checkline create-session-toggle">
        <input
          type="checkbox"
          name="allow_online_booking"
          checked={!isPrivate && allowOnlineBooking}
          disabled={isPrivate}
          onChange={(event) => setAllowOnlineBooking(event.currentTarget.checked)}
        />
        Autoriser la reservation en ligne (creneau public)
      </label>
    </>
  );
}

