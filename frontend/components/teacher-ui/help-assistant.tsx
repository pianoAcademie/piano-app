"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import type { UiLanguage } from "../../lib/ui-i18n";

type HelpTopic = {
  id: string;
  icon: string;
  title: string;
  question: string;
  keywords: string[];
  intro: string;
  steps: string[];
  note?: string;
  href: string;
  action: string;
};

type HelpCopy = {
  launcher: string;
  title: string;
  subtitle: string;
  close: string;
  back: string;
  searchLabel: string;
  searchPlaceholder: string;
  quickQuestions: string;
  results: string;
  noResultTitle: string;
  noResultBody: string;
  contactAdmin: string;
  steps: string;
};

const COPY: Record<UiLanguage, HelpCopy> = {
  fr: {
    launcher: "Aide",
    title: "Aide professeur",
    subtitle: "Comment puis-je vous aider ?",
    close: "Fermer l’aide",
    back: "Retour aux questions",
    searchLabel: "Rechercher dans l’aide",
    searchPlaceholder: "Ex. présence, absence, relevé…",
    quickQuestions: "Questions fréquentes",
    results: "Résultats",
    noResultTitle: "Je n’ai pas encore cette réponse.",
    noResultBody: "Pour une question liée à un cours, ouvrez ce cours dans le planning et utilisez la note interne destinée à l’administration.",
    contactAdmin: "Ouvrir le planning",
    steps: "Étapes",
  },
  en: {
    launcher: "Help",
    title: "Teacher help",
    subtitle: "How can I help you?",
    close: "Close help",
    back: "Back to questions",
    searchLabel: "Search help",
    searchPlaceholder: "E.g. attendance, absence, statement…",
    quickQuestions: "Common questions",
    results: "Results",
    noResultTitle: "I do not have this answer yet.",
    noResultBody: "For a lesson-related question, open the lesson in the schedule and use the internal note for the administration.",
    contactAdmin: "Open the schedule",
    steps: "Steps",
  },
};

const TOPICS: Record<UiLanguage, HelpTopic[]> = {
  fr: [
    {
      id: "attendance",
      icon: "✓",
      title: "Renseigner les présences",
      question: "Comment renseigner la présence des élèves ?",
      keywords: ["présence", "présences", "appel", "élève", "cours", "absent", "attendance"],
      intro: "La saisie se fait directement depuis la liste des présences manquantes ou depuis le cours dans le planning.",
      steps: [
        "Ouvrez l’onglet {{todo}} puis, dans {{today_title}}, sélectionnez le cours marqué {{attendance_booked}}.",
        "Pour chaque élève, sélectionnez {{present}}, {{excused}} ou {{unexcused}}.",
        "Le statut est enregistré dès que vous appuyez sur le bouton. Lorsque tous les élèves sont renseignés, le cours disparaît de {{today_title}}.",
      ],
      href: "/prof?tab=overview",
      action: "Ouvrir {{todo}}",
    },
    {
      id: "student-absence",
      icon: "A",
      title: "Déclarer l’absence d’un élève",
      question: "Comment déclarer l’absence d’un élève ?",
      keywords: ["absence", "élève", "excusée", "non excusée", "absent", "présence"],
      intro: "L’absence d’un élève se renseigne dans la feuille de présence du cours concerné.",
      steps: [
        "Ouvrez le cours depuis {{todo}} ou depuis {{planning}}.",
        "Repérez l’élève concerné dans la liste des inscrits.",
        "Choisissez {{excused}} si l’absence a été signalée, sinon {{unexcused}}.",
      ],
      href: "/prof?tab=overview",
      action: "Ouvrir {{todo}}",
    },
    {
      id: "teacher-absence",
      icon: "!",
      title: "Déclarer mon absence",
      question: "Comment déclarer mon absence de professeur ?",
      keywords: ["mon absence", "professeur absent", "annuler cours", "annulation", "prévenir élèves", "absence prof"],
      intro: "La déclaration annule le cours concerné. Vous pouvez prévenir les élèves au même moment.",
      steps: [
        "Ouvrez {{planning}}, puis le cours concerné.",
        "Dépliez la rubrique {{teacher_absence}}.",
        "Cochez {{notify_students}} si nécessaire, puis vérifiez le sujet et le message.",
        "Ouvrez {{declare_teacher_absence}}, puis appuyez sur {{confirm_teacher_absence}}.",
      ],
      note: "Si la rubrique n’apparaît pas, vous n’avez pas l’autorisation de modifier ce cours : contactez l’administration.",
      href: "/prof?tab=planning",
      action: "Ouvrir le planning",
    },
    {
      id: "validate-statement",
      icon: "€",
      title: "{{approve_statement}}",
      question: "Comment vérifier et approuver mon relevé ?",
      keywords: ["relevé", "valider", "validation", "heures", "prestations", "montant", "facturation"],
      intro: "Le relevé mensuel récapitule vos cours, les présences, les durées et les montants à facturer.",
      steps: [
        "Ouvrez {{statements}} et sélectionnez le mois avec {{previous_month}} ou {{next_month}}.",
        "Vérifiez les lignes de cours, les présences, les durées et les montants HT.",
        "Utilisez {{report_issue}} ou {{add_missing_service}} si une correction est nécessaire.",
        "Lorsque tout est correct, dans {{statement_validation}}, appuyez sur {{approve_statement}}.",
      ],
      note: "La facturation n’est disponible qu’après validation du relevé.",
      href: "/prof/statements",
      action: "Ouvrir mes relevés",
    },
    {
      id: "invoice",
      icon: "🧾",
      title: "Créer ou envoyer ma facture",
      question: "Comment facturer l’école après validation ?",
      keywords: ["facture", "facturer", "comptabilité", "envoyer", "siret", "iban", "relevé"],
      intro: "Après validation du relevé, la rubrique Facturation devient disponible.",
      steps: [
        "Dans {{statements}}, ouvrez le mois concerné et appuyez sur {{approve_statement}}.",
        "Dans {{billing}}, choisissez {{generate_invoice}}, ou {{external_billing}} si vous utilisez votre propre outil.",
        "Vérifiez la facture générée, notamment le SIRET et l’IBAN affichés.",
        "Lorsque tout est correct, appuyez sur {{send_to_accounting}}. Si le SIRET ou l’IBAN est incorrect, contactez d’abord l’administration.",
      ],
      href: "/prof/statements",
      action: "Ouvrir la facturation",
    },
    {
      id: "online-link",
      icon: "↗",
      title: "Trouver le lien du cours en ligne",
      question: "Où trouver le lien Zoom d’un cours ?",
      keywords: ["zoom", "lien", "cours en ligne", "online", "visioconférence", "visio"],
      intro: "Le lien du cours en ligne est associé au créneau dans le planning.",
      steps: [
        "Ouvrez {{planning}} et sélectionnez le cours concerné.",
        "Dépliez {{slot_details}}.",
        "Dans la ligne {{zoom_link}}, appuyez sur {{open_link}}.",
      ],
      note: "Si aucun lien n’est affiché pour un cours en ligne, contactez l’administration avant le début du cours.",
      href: "/prof?tab=planning",
      action: "Ouvrir le planning",
    },
    {
      id: "contact-admin",
      icon: "✉",
      title: "Envoyer une note à l’administration",
      question: "Comment envoyer une note à l’administration au sujet d’un cours ?",
      keywords: ["message", "administration", "aide", "problème", "contacter", "écrire"],
      intro: "La note est liée au cours et n’est jamais envoyée aux élèves ni aux parents.",
      steps: [
        "Ouvrez {{planning}} et sélectionnez le cours concerné.",
        "Dépliez {{admin_note_section}}.",
        "Renseignez {{subject}} et {{internal_note}}, puis appuyez sur {{save_note}}.",
      ],
      href: "/prof?tab=planning",
      action: "Ouvrir {{planning}}",
    },
  ],
  en: [
    {
      id: "attendance",
      icon: "✓",
      title: "Record attendance",
      question: "How do I record student attendance?",
      keywords: ["attendance", "student", "lesson", "present", "absent", "register"],
      intro: "You can record attendance from the missing-attendance list or directly from a lesson in the schedule.",
      steps: [
        "Open {{todo}} and, under {{today_title}}, select the lesson marked {{attendance_booked}}.",
        "For each student, choose {{present}}, {{excused}} or {{unexcused}}.",
        "The status is saved as soon as you press the button. Once all students are recorded, the lesson disappears from {{today_title}}.",
      ],
      href: "/prof?tab=overview",
      action: "Open {{todo}}",
    },
    {
      id: "student-absence",
      icon: "A",
      title: "Record a student absence",
      question: "How do I record a student absence?",
      keywords: ["absence", "student", "excused", "unexcused", "absent", "attendance"],
      intro: "A student absence is recorded in the attendance sheet for the relevant lesson.",
      steps: [
        "Open the lesson from {{todo}} or from {{planning}}.",
        "Find the relevant student in the enrolment list.",
        "Choose {{excused}} if it was reported, otherwise choose {{unexcused}}.",
      ],
      href: "/prof?tab=overview",
      action: "Open {{todo}}",
    },
    {
      id: "teacher-absence",
      icon: "!",
      title: "Report my absence",
      question: "How do I report my absence as a teacher?",
      keywords: ["my absence", "teacher absent", "cancel lesson", "cancellation", "notify students"],
      intro: "Reporting your absence cancels the relevant lesson. You can notify the students at the same time.",
      steps: [
        "Open {{planning}}, then select the relevant lesson.",
        "Expand {{teacher_absence}}.",
        "Select {{notify_students}} if required, then check the subject and message.",
        "Open {{declare_teacher_absence}}, then press {{confirm_teacher_absence}}.",
      ],
      note: "If the section is not shown, you are not allowed to edit this lesson. Please contact the administration.",
      href: "/prof?tab=planning",
      action: "Open the schedule",
    },
    {
      id: "validate-statement",
      icon: "€",
      title: "{{approve_statement}}",
      question: "How do I check and approve my statement?",
      keywords: ["statement", "approve", "validate", "hours", "services", "amount", "billing"],
      intro: "The monthly statement summarises your lessons, attendance, durations and billable amounts.",
      steps: [
        "Open {{statements}} and select the month using {{previous_month}} or {{next_month}}.",
        "Check the lesson lines, attendance, durations and amounts excluding VAT.",
        "Use {{report_issue}} or {{add_missing_service}} if a correction is required.",
        "When everything is correct, press {{approve_statement}} under {{statement_validation}}.",
      ],
      note: "Billing only becomes available after the statement has been approved.",
      href: "/prof/statements",
      action: "Open my statements",
    },
    {
      id: "invoice",
      icon: "🧾",
      title: "Create or send my invoice",
      question: "How do I invoice the school after approval?",
      keywords: ["invoice", "billing", "accounting", "send", "siret", "iban", "statement"],
      intro: "After the statement is approved, the Billing section becomes available.",
      steps: [
        "Under {{statements}}, open the relevant month and press {{approve_statement}}.",
        "Under {{billing}}, choose {{generate_invoice}}, or {{external_billing}} if you use your own software.",
        "Check the generated invoice, including the displayed SIRET and IBAN.",
        "When everything is correct, press {{send_to_accounting}}. If the SIRET or IBAN is incorrect, contact the administration first.",
      ],
      href: "/prof/statements",
      action: "Open billing",
    },
    {
      id: "online-link",
      icon: "↗",
      title: "Find the online lesson link",
      question: "Where can I find a lesson’s Zoom link?",
      keywords: ["zoom", "link", "online lesson", "video", "videoconference"],
      intro: "The online lesson link is attached to the slot in the schedule.",
      steps: [
        "Open {{planning}} and select the relevant lesson.",
        "Expand {{slot_details}}.",
        "On the {{zoom_link}} row, press {{open_link}}.",
      ],
      note: "If no link is shown for an online lesson, contact the administration before the lesson starts.",
      href: "/prof?tab=planning",
      action: "Open the schedule",
    },
    {
      id: "contact-admin",
      icon: "✉",
      title: "Send a note to the administration",
      question: "How do I send the administration a note about a lesson?",
      keywords: ["message", "administration", "help", "problem", "contact", "write"],
      intro: "The note is linked to the lesson and is never sent to students or parents.",
      steps: [
        "Open {{planning}} and select the relevant lesson.",
        "Expand {{admin_note_section}}.",
        "Complete {{subject}} and {{internal_note}}, then press {{save_note}}.",
      ],
      href: "/prof?tab=planning",
      action: "Open {{planning}}",
    },
  ],
};

function normalizeSearch(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase()
    .trim();
}

function withInterfaceLabels(value: string, interfaceLabels: Record<string, string>): string {
  return Object.entries(interfaceLabels).reduce(
    (result, [token, label]) => result.replaceAll(`{{${token}}}`, `« ${label} »`),
    value,
  );
}

function hydrateHelpTopic(topic: HelpTopic, interfaceLabels: Record<string, string>): HelpTopic {
  return {
    ...topic,
    title: withInterfaceLabels(topic.title, interfaceLabels),
    question: withInterfaceLabels(topic.question, interfaceLabels),
    intro: withInterfaceLabels(topic.intro, interfaceLabels),
    steps: topic.steps.map((step) => withInterfaceLabels(step, interfaceLabels)),
    note: topic.note ? withInterfaceLabels(topic.note, interfaceLabels) : undefined,
    action: withInterfaceLabels(topic.action, interfaceLabels),
  };
}

export default function ProfessorHelpAssistant({
  language,
  interfaceLabels,
}: {
  language: UiLanguage;
  interfaceLabels: Record<string, string>;
}): JSX.Element {
  const copy = COPY[language];
  const topics = useMemo(
    () => TOPICS[language].map((topic) => hydrateHelpTopic(topic, interfaceLabels)),
    [interfaceLabels, language],
  );
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  const filteredTopics = useMemo(() => {
    const normalizedQuery = normalizeSearch(query);
    if (!normalizedQuery) {
      return topics;
    }
    const words = normalizedQuery.split(/\s+/).filter(Boolean);
    return topics.filter((topic) => {
      const searchable = normalizeSearch([topic.title, topic.question, topic.intro, ...topic.keywords].join(" "));
      return words.every((word) => searchable.includes(word));
    });
  }, [query, topics]);

  const selectedTopic = selectedId ? topics.find((topic) => topic.id === selectedId) ?? null : null;

  const close = () => {
    setOpen(false);
    setSelectedId(null);
    setQuery("");
  };

  return (
    <div className={`prof-help ${open ? "is-open" : ""}`}>
      {open ? (
        <aside className="prof-help-panel" id="prof-help-panel" role="dialog" aria-labelledby="prof-help-title">
          <header className="prof-help-header">
            <div>
              <p className="prof-help-kicker">Piano Academie</p>
              <h2 id="prof-help-title">{copy.title}</h2>
              <p>{copy.subtitle}</p>
            </div>
            <button type="button" className="prof-help-close" onClick={close} aria-label={copy.close}>
              ×
            </button>
          </header>

          <div className="prof-help-body">
            {selectedTopic ? (
              <article className="prof-help-answer">
                <button type="button" className="prof-help-back" onClick={() => setSelectedId(null)}>
                  ← {copy.back}
                </button>
                <div className="prof-help-answer-title">
                  <span className="prof-help-answer-icon" aria-hidden="true">{selectedTopic.icon}</span>
                  <h3>{selectedTopic.question}</h3>
                </div>
                <p>{selectedTopic.intro}</p>
                <h4>{copy.steps}</h4>
                <ol>
                  {selectedTopic.steps.map((step) => <li key={step}>{step}</li>)}
                </ol>
                {selectedTopic.note ? <p className="prof-help-note">{selectedTopic.note}</p> : null}
                <Link className="prof-help-action" href={selectedTopic.href} onClick={close}>
                  {selectedTopic.action} →
                </Link>
              </article>
            ) : (
              <>
                <label className="prof-help-search">
                  <span>{copy.searchLabel}</span>
                  <div>
                    <span aria-hidden="true">⌕</span>
                    <input
                      type="search"
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      placeholder={copy.searchPlaceholder}
                      autoFocus
                    />
                  </div>
                </label>

                <h3 className="prof-help-list-title">{query ? copy.results : copy.quickQuestions}</h3>
                {filteredTopics.length > 0 ? (
                  <div className="prof-help-topics">
                    {filteredTopics.map((topic) => (
                      <button key={topic.id} type="button" className="prof-help-topic" onClick={() => setSelectedId(topic.id)}>
                        <span className="prof-help-topic-icon" aria-hidden="true">{topic.icon}</span>
                        <span>
                          <strong>{topic.title}</strong>
                          <small>{topic.question}</small>
                        </span>
                        <span className="prof-help-topic-arrow" aria-hidden="true">›</span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="prof-help-empty">
                    <strong>{copy.noResultTitle}</strong>
                    <p>{copy.noResultBody}</p>
                    <Link href="/prof?tab=planning" onClick={close}>{copy.contactAdmin} →</Link>
                  </div>
                )}
              </>
            )}
          </div>
        </aside>
      ) : null}

      <button
        type="button"
        className="prof-help-launcher"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls="prof-help-panel"
        aria-label={open ? copy.close : copy.title}
      >
        <span className="prof-help-launcher-icon" aria-hidden="true">?</span>
        <span>{copy.launcher}</span>
      </button>
    </div>
  );
}
