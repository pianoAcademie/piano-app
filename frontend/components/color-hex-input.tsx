"use client";

import { useState } from "react";

type ColorHexInputProps = {
  name: string;
  defaultValue?: string;
};

function normalizeHex(raw: string | null | undefined): string {
  const candidate = String(raw ?? "").trim().toUpperCase();
  if (!candidate) {
    return "#94C973";
  }
  const prefixed = candidate.startsWith("#") ? candidate : `#${candidate}`;
  if (!/^#[0-9A-F]{6}$/.test(prefixed)) {
    return "#94C973";
  }
  return prefixed;
}

function parseHex(raw: string): string | null {
  const candidate = raw.trim().toUpperCase();
  if (!candidate) {
    return null;
  }
  const prefixed = candidate.startsWith("#") ? candidate : `#${candidate}`;
  if (!/^#[0-9A-F]{6}$/.test(prefixed)) {
    return null;
  }
  return prefixed;
}

export default function ColorHexInput({ name, defaultValue }: ColorHexInputProps): JSX.Element {
  const initial = normalizeHex(defaultValue);
  const [value, setValue] = useState(initial);
  const [textValue, setTextValue] = useState(initial);

  return (
    <div className="activity-color-control">
      <input type="hidden" name={name} value={value} />
      <input
        type="color"
        value={value}
        onChange={(event) => {
          const next = normalizeHex(event.target.value);
          setValue(next);
          setTextValue(next);
        }}
      />
      <input
        className="activity-color-hex"
        type="text"
        value={textValue}
        maxLength={7}
        onChange={(event) => {
          const raw = event.target.value.toUpperCase();
          setTextValue(raw);
          const maybe = parseHex(raw);
          if (maybe) {
            setValue(maybe);
          }
        }}
        onBlur={() => {
          const maybe = parseHex(textValue);
          if (maybe) {
            setTextValue(maybe);
            setValue(maybe);
            return;
          }
          setTextValue(value);
        }}
      />
      <span className="activity-color-swatch" style={{ backgroundColor: value }} aria-hidden />
    </div>
  );
}
