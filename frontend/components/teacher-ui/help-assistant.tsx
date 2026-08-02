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
    noResultBody: "Vous pouvez envoyer votre question à l’administration depuis la messagerie professeur.",
    contactAdmin: "Écrire à l’administration",
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
    noResultBody: "You can send your question to the administration from the teacher messaging area.",
    contactAdmin: "Contact administration",
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
        "Ouvrez l’onglet À faire et choisissez un cours dans Présences à renseigner.",
        "Pour chaque élève, sélectionnez Présent, Absence excusée ou Absence non excusée.",
        "Le statut est enregistré dès que vous appuyez sur le bouton. Lorsque tous les élèves sont renseignés, le cours disparaît de la liste À faire.",
      ],
      href: "/prof?tab=overview",
      action: "Ouvrir les présences à renseigner",
    },
    {
      id: "student-absence",
      icon: "A",
      title: "Déclarer l’absence d’un élève",
      question: "Comment déclarer l’absence d’un élève ?",
      keywords: ["absence", "élève", "excusée", "non excusée", "absent", "présence"],
      intro: "L’absence d’un élève se renseigne dans la feuille de présence du cours concerné.",
      steps: [
        "Ouvrez le cours depuis À faire ou depuis le Planning.",
        "Repérez l’élève concerné dans la liste des inscrits.",
        "Choisissez Absence excusée si l’absence a été signalée, sinon Absence non excusée.",
      ],
      href: "/prof?tab=overview",
      action: "Ouvrir mes tâches",
    },
    {
      id: "teacher-absence",
      icon: "!",
      title: "Déclarer mon absence",
      question: "Comment déclarer mon absence de professeur ?",
      keywords: ["mon absence", "professeur absent", "annuler cours", "annulation", "prévenir élèves", "absence prof"],
      intro: "La déclaration annule le cours concerné. Vous pouvez prévenir les élèves au même moment.",
      steps: [
        "Ouvrez le Planning, puis le cours concerné.",
        "Dépliez la rubrique Absence du professeur.",
        "Choisissez si les élèves doivent être prévenus et vérifiez le message.",
        "Ouvrez la confirmation, puis appuyez sur Confirmer l’absence du professeur.",
      ],
      note: "Si la rubrique n’apparaît pas, vous n’avez pas l’autorisation de modifier ce cours : contactez l’administration.",
      href: "/prof?tab=planning",
      action: "Ouvrir le planning",
    },
    {
      id: "validate-statement",
      icon: "€",
      title: "Valider mon relevé",
      question: "Comment vérifier et valider mon relevé ?",
      keywords: ["relevé", "valider", "validation", "heures", "prestations", "montant", "facturation"],
      intro: "Le relevé mensuel récapitule vos cours, les présences, les durées et les montants à facturer.",
      steps: [
        "Ouvrez Relevés et sélectionnez le mois avec les boutons Mois précédent ou Mois suivant.",
        "Vérifiez les lignes de cours, les présences, les durées et les montants HT.",
        "Utilisez Signaler un problème ou Ajouter une prestation manquante si une correction est nécessaire.",
        "Lorsque tout est correct, appuyez sur Valider mon relevé dans la rubrique Validation du relevé.",
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
        "Vérifiez d’abord que vos informations professionnelles, votre SIRET et votre IBAN sont à jour dans Profil.",
        "Dans Relevés, validez le mois concerné.",
        "Choisissez Générer la facture, ou Facturation externe si vous utilisez votre propre outil.",
        "Vérifiez le PDF, puis appuyez sur Envoyer à la comptabilité.",
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
        "Ouvrez le Planning et sélectionnez le cours concerné.",
        "Dépliez Détails du créneau.",
        "Dans la ligne Lien Zoom, appuyez sur Ouvrir le lien.",
      ],
      note: "Si aucun lien n’est affiché pour un cours en ligne, contactez l’administration avant le début du cours.",
      href: "/prof?tab=planning",
      action: "Ouvrir le planning",
    },
    {
      id: "contact-admin",
      icon: "✉",
      title: "Contacter l’administration",
      question: "Comment envoyer un message à l’administration ?",
      keywords: ["message", "administration", "aide", "problème", "contacter", "écrire"],
      intro: "La messagerie professeur permet de conserver votre échange dans l’application.",
      steps: [
        "Ouvrez Messages.",
        "Choisissez Administration comme destinataire.",
        "Rédigez l’objet et votre message, puis envoyez-le.",
      ],
      href: "/prof?tab=messages",
      action: "Ouvrir la messagerie",
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
        "Open To do and select a lesson under Attendance to complete.",
        "For each student, choose Present, Excused absence or Unexcused absence.",
        "The status is saved as soon as you press the button. Once all students are recorded, the lesson disappears from the To do list.",
      ],
      href: "/prof?tab=overview",
      action: "Open attendance to complete",
    },
    {
      id: "student-absence",
      icon: "A",
      title: "Record a student absence",
      question: "How do I record a student absence?",
      keywords: ["absence", "student", "excused", "unexcused", "absent", "attendance"],
      intro: "A student absence is recorded in the attendance sheet for the relevant lesson.",
      steps: [
        "Open the lesson from To do or from the Schedule.",
        "Find the relevant student in the enrolment list.",
        "Choose Excused absence if it was reported, otherwise choose Unexcused absence.",
      ],
      href: "/prof?tab=overview",
      action: "Open my tasks",
    },
    {
      id: "teacher-absence",
      icon: "!",
      title: "Report my absence",
      question: "How do I report my absence as a teacher?",
      keywords: ["my absence", "teacher absent", "cancel lesson", "cancellation", "notify students"],
      intro: "Reporting your absence cancels the relevant lesson. You can notify the students at the same time.",
      steps: [
        "Open the Schedule, then select the relevant lesson.",
        "Expand the Teacher absence section.",
        "Choose whether students should be notified and check the message.",
        "Open the confirmation and press Confirm teacher absence.",
      ],
      note: "If the section is not shown, you are not allowed to edit this lesson. Please contact the administration.",
      href: "/prof?tab=planning",
      action: "Open the schedule",
    },
    {
      id: "validate-statement",
      icon: "€",
      title: "Approve my statement",
      question: "How do I check and approve my statement?",
      keywords: ["statement", "approve", "validate", "hours", "services", "amount", "billing"],
      intro: "The monthly statement summarises your lessons, attendance, durations and billable amounts.",
      steps: [
        "Open Statements and select the month using Previous month or Next month.",
        "Check the lesson lines, attendance, durations and amounts excluding VAT.",
        "Use Report an issue or Add a missing service if a correction is required.",
        "When everything is correct, press Approve my statement in the Statement approval section.",
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
        "First check that your business details, SIRET and IBAN are up to date under Profile.",
        "Open Statements and approve the relevant month.",
        "Choose Generate invoice, or External billing if you use your own invoicing tool.",
        "Check the PDF, then press Send to accounting.",
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
        "Open the Schedule and select the relevant lesson.",
        "Expand Slot details.",
        "On the Zoom link row, press Open link.",
      ],
      note: "If no link is shown for an online lesson, contact the administration before the lesson starts.",
      href: "/prof?tab=planning",
      action: "Open the schedule",
    },
    {
      id: "contact-admin",
      icon: "✉",
      title: "Contact administration",
      question: "How do I send a message to the administration?",
      keywords: ["message", "administration", "help", "problem", "contact", "write"],
      intro: "Teacher messaging keeps your conversation available in the application.",
      steps: [
        "Open Messages.",
        "Choose Administration as the recipient.",
        "Write the subject and message, then send it.",
      ],
      href: "/prof?tab=messages",
      action: "Open messaging",
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

export default function ProfessorHelpAssistant({ language }: { language: UiLanguage }): JSX.Element {
  const copy = COPY[language];
  const topics = TOPICS[language];
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
                    <Link href="/prof?tab=messages" onClick={close}>{copy.contactAdmin} →</Link>
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
