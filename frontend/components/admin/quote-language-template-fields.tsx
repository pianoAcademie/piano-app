"use client";

import { useEffect, useMemo, useState } from "react";

type TemplateOption = {
  id: string;
  name: string;
  language?: string | null;
};

type Labels = {
  quoteTemplate: string;
  none: string;
  termsTemplate: string;
  keepCurrentSnapshot: string;
  language: string;
  french: string;
  english: string;
};

type Props = {
  canEdit: boolean;
  initialLanguage: string;
  initialQuoteTemplateId: string;
  initialTermsTemplateId: string;
  labels: Labels;
  quoteTemplates: TemplateOption[];
  termsTemplates: TemplateOption[];
};

function normalizeLang(value: string | null | undefined): "fr" | "en" {
  return String(value || "").trim().toLowerCase() === "en" ? "en" : "fr";
}

export function QuoteLanguageTemplateFields({
  canEdit,
  initialLanguage,
  initialQuoteTemplateId,
  initialTermsTemplateId,
  labels,
  quoteTemplates,
  termsTemplates,
}: Props) {
  const [language, setLanguage] = useState<"fr" | "en">(normalizeLang(initialLanguage));
  const [quoteTemplateId, setQuoteTemplateId] = useState(initialQuoteTemplateId);
  const [termsTemplateId, setTermsTemplateId] = useState(initialTermsTemplateId);

  const languageQuoteTemplates = useMemo(
    () => quoteTemplates.filter((row) => normalizeLang(row.language) === language),
    [language, quoteTemplates],
  );
  const languageTermsTemplates = useMemo(
    () => termsTemplates.filter((row) => normalizeLang(row.language) === language),
    [language, termsTemplates],
  );

  useEffect(() => {
    if (quoteTemplateId && !languageQuoteTemplates.some((row) => row.id === quoteTemplateId)) {
      setQuoteTemplateId("");
    }
    if (termsTemplateId && !languageTermsTemplates.some((row) => row.id === termsTemplateId)) {
      setTermsTemplateId("");
    }
  }, [languageQuoteTemplates, languageTermsTemplates, quoteTemplateId, termsTemplateId]);

  return (
    <>
      <label>
        {labels.quoteTemplate}
        <select
          name="quote_template_uuid"
          value={quoteTemplateId}
          onChange={(event) => setQuoteTemplateId(event.target.value)}
          disabled={!canEdit}
        >
          <option value="">{labels.none}</option>
          {languageQuoteTemplates.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        {labels.termsTemplate}
        <select
          name="terms_template_id"
          value={termsTemplateId}
          onChange={(event) => setTermsTemplateId(event.target.value)}
          disabled={!canEdit}
        >
          <option value="">{labels.keepCurrentSnapshot}</option>
          {languageTermsTemplates.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        {labels.language}
        <select
          name="language"
          value={language}
          onChange={(event) => setLanguage(normalizeLang(event.target.value))}
          disabled={!canEdit}
        >
          <option value="fr">{labels.french}</option>
          <option value="en">{labels.english}</option>
        </select>
      </label>
    </>
  );
}
