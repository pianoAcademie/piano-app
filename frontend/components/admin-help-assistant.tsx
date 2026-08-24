"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import type { UiLanguage } from "../lib/ui-i18n";

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
  fallbackAction: string;
  steps: string;
};

const COPY: Record<UiLanguage, HelpCopy> = {
  fr: {
    launcher: "Aide",
    title: "Aide administration",
    subtitle: "Retrouvez les procédures essentielles de l’école.",
    close: "Fermer l’aide",
    back: "Retour aux questions",
    searchLabel: "Rechercher dans l’aide",
    searchPlaceholder: "Ex. avoir, chèque, planning…",
    quickQuestions: "Procédures fréquentes",
    results: "Résultats",
    noResultTitle: "Aucune procédure ne correspond à cette recherche.",
    noResultBody: "Consultez la liste des opérations à traiter ou contactez la personne responsable de cette procédure.",
    fallbackAction: "Ouvrir les opérations à traiter",
    steps: "Étapes",
  },
  en: {
    launcher: "Help",
    title: "Administration help",
    subtitle: "Find the school’s essential procedures.",
    close: "Close help",
    back: "Back to questions",
    searchLabel: "Search help",
    searchPlaceholder: "E.g. credit note, check, schedule…",
    quickQuestions: "Common procedures",
    results: "Results",
    noResultTitle: "No procedure matches this search.",
    noResultBody: "Check the operations to process or contact the person responsible for this procedure.",
    fallbackAction: "Open operations to process",
    steps: "Steps",
  },
};

const TOPICS: Record<UiLanguage, HelpTopic[]> = {
  fr: [
    {
      id: "credit-note",
      icon: "A",
      title: "Créer un avoir",
      question: "Comment corriger une facture déjà émise ?",
      keywords: ["avoir", "annuler", "facture", "correction", "remboursement", "erreur", "credit note"],
      intro: "Une facture officiellement émise ne doit pas être supprimée. La correction se fait avec un avoir qui conserve la traçabilité comptable.",
      steps: [
        "Ouvrez Clients, sélectionnez le responsable, puis l’onglet Factures.",
        "Sur la facture concernée, appuyez sur le bouton A.",
        "Vérifiez le numéro, le montant et le motif, puis confirmez la création de l’avoir.",
        "Le système crée un avoir numéroté avec des montants négatifs, le relie à la facture d’origine et annule cette facture.",
        "Si le client doit recevoir le document, utilisez ensuite l’action d’envoi par e-mail : aucun e-mail n’est envoyé automatiquement.",
      ],
      note: "Un remboursement bancaire et un avoir sont deux opérations distinctes : le remboursement constate le mouvement d’argent, l’avoir corrige la facture.",
      href: "/admin/clients",
      action: "Ouvrir les clients",
    },
    {
      id: "recurring-invoice",
      icon: "↻",
      title: "Facturer chaque mois ou tous les deux mois",
      question: "Comment remplacer une facture annuelle par une facturation périodique ?",
      keywords: ["mensuel", "bimestriel", "deux mois", "périodique", "échéance", "virement", "carte", "facture automatique"],
      intro: "La facturation automatique permet d’émettre des factures mensuelles, bimestrielles, trimestrielles ou annuelles, réglables par carte bancaire ou par virement.",
      steps: [
        "Si une facture annuelle a déjà été émise, créez d’abord son avoir depuis l’onglet Factures.",
        "Dans la fiche client, appuyez sur Créer la facture puis choisissez Facturation automatique.",
        "Renseignez la date de début, la fréquence mensuelle ou tous les deux mois, la date de fin et la règle d’échéance.",
        "Sélectionnez l’entité légale et toutes les prestations qui doivent entrer dans le cycle.",
        "Vérifiez la première période : elle peut inclure la période déjà écoulée si un rattrapage est nécessaire, puis confirmez.",
      ],
      note: "N’émettez pas en parallèle une facture annuelle et des factures périodiques pour les mêmes prestations et la même période.",
      href: "/admin/clients",
      action: "Configurer un client",
    },
    {
      id: "payment-and-invoice",
      icon: "€",
      title: "Comprendre facture et paiement",
      question: "Quand une facture doit-elle être marquée comme payée ?",
      keywords: ["payée", "paiement", "solde", "règlement", "facture", "rapprochement", "relance"],
      intro: "La facture constate ce qui est dû ; le paiement constate l’argent reçu. Le paiement doit être rapproché de la bonne facture.",
      steps: [
        "Dans Compte, vérifiez le montant, le mode de paiement, la date et le bénéficiaire du règlement.",
        "Rapprochez le règlement de la facture correspondante.",
        "Une facture est payée lorsque les règlements confirmés et encaissés couvrent son montant total.",
        "Dans Factures, vérifiez ensuite que le solde restant est nul et que l’action proposée est Voir, et non Payer.",
      ],
      note: "Pour des chèques reçus mais déposés plus tard, les relances peuvent être suspendues dès la réception. La facture n’est toutefois payée qu’au fur et à mesure de l’encaissement effectif.",
      href: "/admin/clients",
      action: "Ouvrir les comptes clients",
    },
    {
      id: "check-workflow",
      icon: "CHQ",
      title: "Recevoir et déposer des chèques",
      question: "Quel workflow utiliser pour les chèques ?",
      keywords: ["chèque", "chèques", "richelieu", "bar-le-duc", "administration", "dépôt", "encaissement", "banque"],
      intro: "Le lieu de réception détermine le circuit physique du chèque. Tous les chèques déjà saisis avant la mise en place de ce workflow sont considérés comme étant entre les mains de l’administration.",
      steps: [
        "Dans Compte, ajoutez un paiement par chèque et rapprochez-le de la facture concernée.",
        "Choisissez Rue de Richelieu si le chèque doit être transmis à l’administration, ou Bar-le-Duc s’il est prêt pour une remise locale.",
        "Renseignez le mois et l’année de dépôt prévus, puis enregistrez la réception.",
        "Dans Dépôts de chèques, suivez ensuite le passage de Reçu à Administration, Déposé puis Encaissé.",
        "Marquez la facture payée uniquement à hauteur des chèques effectivement encaissés.",
      ],
      note: "La réception des chèques suspend les relances sur le montant couvert, mais elle ne constitue pas encore un encaissement bancaire.",
      href: "/admin/check-deposits",
      action: "Ouvrir les dépôts de chèques",
    },
    {
      id: "refund",
      icon: "↩",
      title: "Enregistrer un remboursement",
      question: "Comment enregistrer correctement un remboursement client ?",
      keywords: ["remboursement", "trop-perçu", "virement", "avoir", "sortie", "argent"],
      intro: "Le remboursement doit refléter le mouvement bancaire réel. S’il corrige une prestation facturée, il doit aussi être accompagné d’un avoir.",
      steps: [
        "Effectuez d’abord le remboursement auprès du prestataire de paiement ou par virement bancaire.",
        "Dans Compte, ajoutez une transaction de type Remboursement avec la date, le montant et la référence bancaire.",
        "Si la somme correspond à une facture, ouvrez Factures et créez l’avoir correspondant.",
        "Vérifiez que le remboursement apparaît en négatif dans les transactions et que l’avoir est téléchargeable.",
      ],
      href: "/admin/clients",
      action: "Ouvrir les clients",
    },
    {
      id: "invoice-reminder",
      icon: "✉",
      title: "Envoyer une facture ou une relance",
      question: "Quand et comment envoyer une relance ?",
      keywords: ["relance", "email", "e-mail", "envoyer facture", "impayé", "communication"],
      intro: "Les actions d’envoi se trouvent sur chaque facture. Vérifiez toujours son statut et son solde avant de contacter le client.",
      steps: [
        "Ouvrez Clients, la fiche du responsable, puis Factures.",
        "Vérifiez que la facture est émise, non annulée, non créditée et qu’un solde reste réellement dû.",
        "Utilisez l’action d’envoi ou de relance, puis contrôlez le destinataire, l’objet et le contenu du message.",
        "N’envoyez pas de relance si des chèques reçus couvrent déjà le solde ou si un remboursement/avoir est en cours de traitement.",
      ],
      href: "/admin/clients",
      action: "Vérifier une facture",
    },
    {
      id: "series-notifications",
      icon: "🔔",
      title: "Modifier une série sans notifier par erreur",
      question: "Comment ajouter ou retirer un élève d’une série ?",
      keywords: ["série", "planning", "ajouter élève", "retirer élève", "notification", "email", "administratif"],
      intro: "Lors d’une manipulation administrative sur une série, l’administrateur choisit explicitement si le client doit recevoir un e-mail.",
      steps: [
        "Ouvrez le créneau dans le planning et ajoutez ou retirez le bénéficiaire sur la série.",
        "Vérifiez les occurrences concernées et la date de fin de série.",
        "À la confirmation, choisissez Envoyer un e-mail uniquement si le client doit réellement être informé.",
        "Pour une correction ou une migration interne, choisissez Ne pas envoyer d’e-mail afin d’éviter une série de notifications inutiles.",
      ],
      href: "/admin",
      action: "Ouvrir le planning",
    },
    {
      id: "masterclass-teachers",
      icon: "4P",
      title: "Affecter plusieurs professeurs à une Masterclass",
      question: "Comment gérer jusqu’à quatre professeurs sur une Masterclass ?",
      keywords: ["masterclass", "professeur", "professeurs", "multi", "présence", "rappel", "rémunération"],
      intro: "Une Masterclass peut être attribuée à quatre professeurs au maximum. Chacun est rémunéré au tarif prévu pour l’activité.",
      steps: [
        "Ouvrez ou modifiez le créneau Masterclass dans le planning.",
        "Sélectionnez les professeurs concernés dans les champs d’affectation, sans dépasser quatre personnes.",
        "Vérifiez l’affectation dans Besoins professeurs et la vue de charge de chaque professeur.",
        "Chaque professeur verra le cours dans son rappel matinal et pourra saisir la présence des élèves.",
      ],
      href: "/admin/simulation-planning",
      action: "Ouvrir les besoins professeurs",
    },
    {
      id: "intake-review",
      icon: "TF",
      title: "Contrôler un questionnaire Typeform",
      question: "Que vérifier avant de créer le devis ?",
      keywords: ["typeform", "intake", "questionnaire", "horaire", "synthèse", "devis", "enfant"],
      intro: "La synthèse aide à préparer le devis, mais les réponses détaillées du questionnaire restent la source à contrôler avant validation.",
      steps: [
        "Ouvrez Intakes puis la réponse concernée.",
        "Comparez l’enfant, le site, les activités, les niveaux et tous les créneaux de la synthèse avec les réponses brutes.",
        "Utilisez Corriger / compléter si une heure ou une information a été mal interprétée.",
        "Vérifiez les avertissements et blocages, puis ouvrez le devis seulement lorsque la synthèse est correcte.",
      ],
      href: "/admin/intakes",
      action: "Ouvrir les intakes",
    },
  ],
  en: [
    {
      id: "credit-note",
      icon: "CN",
      title: "Create a credit note",
      question: "How do I correct an invoice that has already been issued?",
      keywords: ["credit note", "cancel", "invoice", "correction", "refund", "error"],
      intro: "A formally issued invoice must not be deleted. Use a credit note to preserve the accounting audit trail.",
      steps: [
        "Open Clients, select the account holder, then open Invoices.",
        "Press the A button on the relevant invoice.",
        "Check the number, amount and reason, then confirm the credit note.",
        "The system creates a numbered document with negative lines, links it to the original invoice and cancels that invoice.",
        "Use the email action afterwards if the client should receive it; no email is sent automatically.",
      ],
      note: "A bank refund and a credit note are separate operations: one records the cash movement, the other corrects the invoice.",
      href: "/admin/clients",
      action: "Open clients",
    },
    {
      id: "recurring-invoice",
      icon: "↻",
      title: "Invoice monthly or every two months",
      question: "How do I replace an annual invoice with recurring billing?",
      keywords: ["monthly", "bimonthly", "two months", "recurring", "due date", "transfer", "card", "automatic invoice"],
      intro: "Automatic billing supports monthly, two-monthly, quarterly or annual invoices payable by card or bank transfer.",
      steps: [
        "If an annual invoice was already issued, create its credit note first.",
        "On the client record, press Create invoice and choose Automatic billing.",
        "Enter the start date, frequency, end date and payment due-date rule.",
        "Select the legal entity and all services included in the cycle.",
        "Check the first period, including any required catch-up period, then confirm.",
      ],
      note: "Do not keep an annual invoice and recurring invoices active for the same services and period.",
      href: "/admin/clients",
      action: "Configure a client",
    },
    {
      id: "payment-and-invoice",
      icon: "€",
      title: "Understand invoices and payments",
      question: "When should an invoice be marked as paid?",
      keywords: ["paid", "payment", "balance", "invoice", "reconciliation", "reminder"],
      intro: "The invoice records what is due; the payment records money received. Link the payment to the correct invoice.",
      steps: [
        "Under Account, check the payment amount, method, date and beneficiary.",
        "Reconcile the payment with the correct invoice.",
        "An invoice is paid when confirmed and cleared payments cover its full amount.",
        "Under Invoices, check that the remaining balance is zero and the available action is View, not Pay.",
      ],
      note: "Received checks can suspend reminders, but the invoice is only paid as the checks are actually cleared.",
      href: "/admin/clients",
      action: "Open client accounts",
    },
    {
      id: "check-workflow",
      icon: "CHK",
      title: "Receive and deposit checks",
      question: "Which workflow should I use for checks?",
      keywords: ["check", "checks", "richelieu", "bar-le-duc", "administration", "deposit", "cleared", "bank"],
      intro: "The reception location determines the physical check workflow. Checks entered before this workflow was introduced are considered to be held by the administration.",
      steps: [
        "Under Account, add a check payment and link it to the relevant invoice.",
        "Choose Rue de Richelieu if it must be sent to the administration, or Bar-le-Duc if it is ready for local deposit.",
        "Enter the expected deposit month and year, then record receipt.",
        "Under Check deposits, move it through Received, Administration, Deposited and Cleared.",
        "Mark the invoice as paid only for checks that have actually cleared.",
      ],
      note: "Receiving a check suspends reminders for the covered amount, but does not yet constitute bank settlement.",
      href: "/admin/check-deposits",
      action: "Open check deposits",
    },
    {
      id: "refund",
      icon: "↩",
      title: "Record a refund",
      question: "How do I correctly record a client refund?",
      keywords: ["refund", "overpayment", "transfer", "credit note", "cash out"],
      intro: "The refund must match the actual bank movement. If it corrects an invoiced service, create a credit note as well.",
      steps: [
        "First issue the refund through the payment provider or by bank transfer.",
        "Under Account, add a Refund transaction with its date, amount and bank reference.",
        "If the amount relates to an invoice, open Invoices and create the matching credit note.",
        "Check that the refund appears as a negative transaction and the credit note can be downloaded.",
      ],
      href: "/admin/clients",
      action: "Open clients",
    },
    {
      id: "invoice-reminder",
      icon: "✉",
      title: "Send an invoice or reminder",
      question: "When and how should I send a reminder?",
      keywords: ["reminder", "email", "send invoice", "unpaid", "communication"],
      intro: "Email actions are available on each invoice. Always check its status and balance first.",
      steps: [
        "Open Clients, the account holder’s record, then Invoices.",
        "Check that the invoice is issued, not cancelled or credited, and that money is genuinely still due.",
        "Use the send or reminder action and check the recipient, subject and message.",
        "Do not send a reminder if received checks already cover the balance or a refund/credit note is being processed.",
      ],
      href: "/admin/clients",
      action: "Check an invoice",
    },
    {
      id: "series-notifications",
      icon: "🔔",
      title: "Edit a series without sending unwanted emails",
      question: "How do I add or remove a student from a series?",
      keywords: ["series", "schedule", "add student", "remove student", "notification", "email", "administrative"],
      intro: "For an administrative series change, the administrator explicitly chooses whether the client receives an email.",
      steps: [
        "Open the slot in the schedule and add or remove the beneficiary from the series.",
        "Check the affected occurrences and series end date.",
        "At confirmation, choose Send email only if the client should genuinely be notified.",
        "For an internal correction or migration, choose Do not send email to avoid unnecessary notifications.",
      ],
      href: "/admin",
      action: "Open the schedule",
    },
    {
      id: "masterclass-teachers",
      icon: "4T",
      title: "Assign several teachers to a Masterclass",
      question: "How do I manage up to four Masterclass teachers?",
      keywords: ["masterclass", "teacher", "teachers", "attendance", "reminder", "payment"],
      intro: "A Masterclass can have up to four teachers. Each is paid at the activity rate.",
      steps: [
        "Open or edit the Masterclass slot in the schedule.",
        "Select the relevant teachers in the assignment fields, up to four people.",
        "Check the assignments under Teacher needs and each teacher’s workload view.",
        "Every teacher will receive the lesson in their morning reminder and can record student attendance.",
      ],
      href: "/admin/simulation-planning",
      action: "Open teacher needs",
    },
    {
      id: "intake-review",
      icon: "TF",
      title: "Review a Typeform intake",
      question: "What should I check before creating a quote?",
      keywords: ["typeform", "intake", "questionnaire", "time", "summary", "quote", "child"],
      intro: "The summary helps prepare a quote, but the questionnaire’s detailed answers remain the source to check before approval.",
      steps: [
        "Open Intakes and select the response.",
        "Compare the child, site, activities, levels and every time slot in the summary with the raw answers.",
        "Use Correct / complete if a time or other information was misinterpreted.",
        "Check warnings and blockers, then open the quote only when the summary is correct.",
      ],
      href: "/admin/intakes",
      action: "Open intakes",
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

export default function AdminHelpAssistant({ language }: { language: UiLanguage }): JSX.Element {
  const copy = COPY[language];
  const topics = TOPICS[language];
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        searchInputRef.current?.blur();
        setOpen(false);
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
      document.body.style.overflow = previousOverflow;
    };
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
    searchInputRef.current?.blur();
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }
    setOpen(false);
    setSelectedId(null);
    setQuery("");
  };

  return (
    <div className={`prof-help ${open ? "is-open" : ""}`}>
      {open ? (
        <aside className="prof-help-panel" id="admin-help-panel" role="dialog" aria-labelledby="admin-help-title">
          <header className="prof-help-header">
            <div>
              <p className="prof-help-kicker">Piano Académie</p>
              <h2 id="admin-help-title">{copy.title}</h2>
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
                      ref={searchInputRef}
                      type="search"
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      placeholder={copy.searchPlaceholder}
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
                    <Link href="/admin/a-traiter" onClick={close}>{copy.fallbackAction} →</Link>
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
        aria-controls="admin-help-panel"
        aria-label={open ? copy.close : copy.title}
      >
        <span className="prof-help-launcher-icon" aria-hidden="true">?</span>
        <span>{copy.launcher}</span>
      </button>
    </div>
  );
}
