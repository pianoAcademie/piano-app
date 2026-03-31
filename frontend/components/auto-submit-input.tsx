"use client";

type AutoSubmitInputProps = {
  name: string;
  type?: "date" | "text";
  defaultValue: string;
  required?: boolean;
  ariaLabel?: string;
};

export default function AutoSubmitInput({
  name,
  type = "text",
  defaultValue,
  required = false,
  ariaLabel,
}: AutoSubmitInputProps): JSX.Element {
  return (
    <input
      type={type}
      name={name}
      defaultValue={defaultValue}
      required={required}
      aria-label={ariaLabel}
      onChange={(event) => {
        event.currentTarget.form?.requestSubmit();
      }}
    />
  );
}
