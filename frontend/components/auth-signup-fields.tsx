"use client";

import { useState } from "react";

import { type UiLanguage, uiText } from "../lib/ui-i18n";

type CountryOption = {
  value: string;
  label: string;
};

type AuthSignupFieldsProps = {
  emailHint: string;
  defaultCountry: string;
  countryOptions: CountryOption[];
  language: UiLanguage;
  defaultRegistrationSubjectType?: "self" | "child";
};

export default function AuthSignupFields({
  emailHint,
  defaultCountry,
  countryOptions,
  language,
  defaultRegistrationSubjectType = "self",
}: AuthSignupFieldsProps): JSX.Element {
  const [registrationSubjectType, setRegistrationSubjectType] = useState<"self" | "child">(defaultRegistrationSubjectType);
  const isChildRegistration = registrationSubjectType === "child";
  const contactLabelSuffix = isChildRegistration ? uiText(language, "auth.parent_suffix") : "";

  return (
    <>
      <section className="auth-step-card">
        <h3>{uiText(language, "auth.step_1")}</h3>
        <label>
          {uiText(language, "auth.step_1_subject")}
          <select
            name="registration_subject_type"
            value={registrationSubjectType}
            onChange={(event) => setRegistrationSubjectType(event.target.value === "child" ? "child" : "self")}
            required
          >
            <option value="self">{uiText(language, "auth.step_1_self")}</option>
            <option value="child">{uiText(language, "auth.step_1_child")}</option>
          </select>
        </label>
        <p className="muted">
          {isChildRegistration
            ? uiText(language, "auth.step_1_child_help")
            : uiText(language, "auth.step_1_self_help")}
        </p>
        <label>
          {uiText(language, "auth.first_name", { suffix: contactLabelSuffix })}
          <input type="text" name="first_name" required maxLength={100} autoComplete="given-name" />
        </label>
        <label>
          {uiText(language, "auth.last_name", { suffix: contactLabelSuffix })}
          <input type="text" name="last_name" required maxLength={100} autoComplete="family-name" />
        </label>
        <label>
          {uiText(language, "common.email")}{contactLabelSuffix}
          <input type="email" name="email" required autoComplete="email" defaultValue={emailHint} />
        </label>
        <label>
          {uiText(language, "auth.phone", { suffix: contactLabelSuffix })}
          <input type="tel" name="phone" required maxLength={30} autoComplete="tel" />
        </label>
        <label>
          {uiText(language, "auth.postal_address", { suffix: contactLabelSuffix })}
          <input
            type="text"
            name="address_line"
            required
            maxLength={255}
            autoComplete="street-address"
            placeholder={uiText(language, "auth.street_placeholder")}
          />
        </label>
        <div className="grid cols-2 config-form-grid">
          <label>
            {uiText(language, "auth.postal_code", { suffix: contactLabelSuffix })}
            <input type="text" name="postal_code" required maxLength={20} autoComplete="postal-code" />
          </label>
          <label>
            {uiText(language, "auth.city", { suffix: contactLabelSuffix })}
            <input type="text" name="city" required maxLength={120} autoComplete="address-level2" />
          </label>
        </div>
        <label>
          {uiText(language, "auth.address_country", { suffix: contactLabelSuffix })}
          <select name="address_country" defaultValue={defaultCountry} required autoComplete="country">
            {countryOptions.map((country) => (
              <option key={`address-country-${country.value}`} value={country.value}>
                {country.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          {uiText(language, "auth.residence_country")}
          <select name="residence_country" defaultValue={defaultCountry} required>
            {countryOptions.map((country) => (
              <option key={country.value} value={country.value}>
                {country.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          {uiText(language, "auth.password")}
          <input type="password" name="password" required minLength={8} autoComplete="new-password" />
        </label>

        {isChildRegistration ? (
          <div className="auth-child-details">
            <p className="auth-consent-group-title">{uiText(language, "auth.child_info_title")}</p>
            <p className="muted">{uiText(language, "auth.child_info_help")}</p>
            <label>
              {uiText(language, "auth.child_first_name")}
              <input type="text" name="child_first_name" required={isChildRegistration} maxLength={100} autoComplete="off" />
            </label>
            <label>
              {uiText(language, "auth.child_last_name")}
              <input type="text" name="child_last_name" required={isChildRegistration} maxLength={100} autoComplete="off" />
            </label>
            <label>
              {uiText(language, "auth.child_birth_date")}
              <input type="date" name="child_birth_date" required={isChildRegistration} />
            </label>
          </div>
        ) : null}
      </section>

      <section className="auth-step-card">
        <h3>{uiText(language, "auth.step_2")}</h3>
        <p className="muted">{uiText(language, "auth.photo_help")}</p>
        <label>
          {uiText(language, "auth.photo_input")}
          <input type="file" name="student_photo" accept="image/jpeg,image/jpg,image/png,image/webp" capture="user" />
        </label>
        <p className="muted">{uiText(language, "auth.photo_optional_hint")}</p>
      </section>
    </>
  );
}
