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
};

export default function AutoSubmitSelect({
  name,
  defaultValue,
  options,
  required = false,
}: AutoSubmitSelectProps): JSX.Element {
  return (
    <select
      name={name}
      defaultValue={defaultValue}
      required={required}
      onChange={(event) => {
        event.currentTarget.form?.requestSubmit();
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

