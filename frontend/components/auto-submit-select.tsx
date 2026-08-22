"use client";

type AutoSubmitSelectOption = {
  value: string;
  label: string;
};

type AutoSubmitSelectProps = {
  name: string;
  defaultValue: string;
  options: AutoSubmitSelectOption[];
  required?: boolean;
  clearNamesOnChange?: string[];
};

export default function AutoSubmitSelect({
  name,
  defaultValue,
  options,
  required = false,
  clearNamesOnChange = [],
}: AutoSubmitSelectProps): JSX.Element {
  return (
    <select
      name={name}
      defaultValue={defaultValue}
      required={required}
      onChange={(event) => {
        const form = event.currentTarget.form;
        if (!form) {
          return;
        }
        for (const fieldName of clearNamesOnChange) {
          for (const field of Array.from(form.querySelectorAll(`[name="${CSS.escape(fieldName)}"]`))) {
            field.remove();
          }
        }
        form.requestSubmit();
      }}
    >
      {options.map((option) => (
        <option key={`${name}-${option.value}`} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
