"use client";

import { useState } from "react";

type CountryOption = {
  value: string;
  label: string;
};

type AuthSignupFieldsProps = {
  emailHint: string;
  defaultCountry: string;
  countryOptions: CountryOption[];
};

export default function AuthSignupFields({
  emailHint,
  defaultCountry,
  countryOptions,
}: AuthSignupFieldsProps): JSX.Element {
  const [registrationSubjectType, setRegistrationSubjectType] = useState<"self" | "child">("self");
  const isChildRegistration = registrationSubjectType === "child";
  const contactLabelSuffix = isChildRegistration ? " du parent / responsable" : "";

  return (
    <>
      <section className="auth-step-card">
        <h3>Etape 1 - Informations obligatoires</h3>
        <label>
          Cette inscription concerne
          <select
            name="registration_subject_type"
            value={registrationSubjectType}
            onChange={(event) => setRegistrationSubjectType(event.target.value === "child" ? "child" : "self")}
            required
          >
            <option value="self">Moi-meme</option>
            <option value="child">Mon enfant</option>
          </select>
        </label>
        <p className="muted">
          {isChildRegistration
            ? "Renseignez ici les coordonnees du parent ou responsable legal. Les informations de l enfant seront completees ensuite."
            : "Renseignez ici les informations de la personne qui cree le compte client."}
        </p>
        <label>
          Prenom{contactLabelSuffix}
          <input type="text" name="first_name" required maxLength={100} autoComplete="given-name" />
        </label>
        <label>
          Nom{contactLabelSuffix}
          <input type="text" name="last_name" required maxLength={100} autoComplete="family-name" />
        </label>
        <label>
          Email{contactLabelSuffix}
          <input type="email" name="email" required autoComplete="email" defaultValue={emailHint} />
        </label>
        <label>
          Telephone{contactLabelSuffix}
          <input type="tel" name="phone" required maxLength={30} autoComplete="tel" />
        </label>
        <label>
          Pays de residence
          <select name="residence_country" defaultValue={defaultCountry} required>
            {countryOptions.map((country) => (
              <option key={country.value} value={country.value}>
                {country.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Mot de passe
          <input type="password" name="password" required minLength={8} autoComplete="new-password" />
        </label>
      </section>

      <section className="auth-step-card">
        <h3>Etape 2 - Photo de l eleve (optionnel)</h3>
        <p className="muted">
          Vous pouvez ajouter une photo si vous le souhaitez, mais elle n est pas obligatoire pour finaliser la creation du compte.
        </p>
        <label>
          Prendre une photo (mobile) ou choisir une image
          <input type="file" name="student_photo" accept="image/jpeg,image/jpg,image/png,image/webp" capture="user" />
        </label>
        <p className="muted">Si vous preferez, vous pouvez laisser ce champ vide.</p>
      </section>
    </>
  );
}
