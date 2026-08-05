"use client";

import { useState } from "react";

type AttendanceInternalNoteFieldProps = {
  attendanceFormId: string;
  defaultValue: string;
  placeholder: string;
};

export default function AttendanceInternalNoteField({
  attendanceFormId,
  defaultValue,
  placeholder,
}: AttendanceInternalNoteFieldProps): JSX.Element {
  const [value, setValue] = useState(defaultValue);

  return (
    <>
      <textarea
        name="internal_note"
        rows={4}
        maxLength={12000}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder={placeholder}
      />
      <input type="hidden" name="internal_note" value={value} form={attendanceFormId} />
    </>
  );
}
