import type { Metadata } from "next";
import { headers } from "next/headers";

import { PublicInfoPage } from "../public-info-page";

type SearchParams = Record<string, string | string[] | undefined>;
type SupportLanguage = "fr" | "en";

const CLIENT_APP_IOS_URL = "https://apps.apple.com/fr/app/piano-academie-client/id6772464779";
const CLIENT_APP_ANDROID_URL = "https://play.google.com/store/apps/details?id=com.pianoacademie.client";

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function resolveLanguage(rawLanguage: string, acceptLanguage: string): SupportLanguage {
  for (const candidate of [rawLanguage, acceptLanguage]) {
    const normalized = candidate.trim().toLowerCase();
    if (normalized === "en" || normalized.startsWith("en-")) return "en";
    if (normalized === "fr" || normalized.startsWith("fr-")) return "fr";
  }
  return "fr";
}

function externalLink(href: string, label: string): JSX.Element {
  return (
    <a href={href} target="_blank" rel="noreferrer" style={{ color: "#8a5a16", fontWeight: 700 }}>
      {label}
    </a>
  );
}

export function generateMetadata({ searchParams }: { searchParams: SearchParams }): Metadata {
  const language = resolveLanguage(readParam(searchParams, "lang"), headers().get("accept-language") ?? "");
  return {
    title: language === "en" ? "FAQ and support | Piano Académie" : "FAQ et assistance | Piano Académie",
    description:
      language === "en"
        ? "Help with access, bookings, invoices and payments in the Piano Académie Client app."
        : "Aide pour l’accès, les réservations, les factures et les paiements dans l’application Client Piano Académie.",
    alternates: {
      canonical: "https://app.piano-academie.com/support",
      languages: {
        "fr-FR": "https://app.piano-academie.com/support?lang=fr",
        "en-GB": "https://app.piano-academie.com/support?lang=en",
      },
    },
  };
}

export default function SupportPage({ searchParams }: { searchParams: SearchParams }): JSX.Element {
  const language = resolveLanguage(readParam(searchParams, "lang"), headers().get("accept-language") ?? "");

  if (language === "en") {
    return (
      <PublicInfoPage
        eyebrow="FAQ & support"
        title="Piano Académie help"
        intro="Find answers about your client account, the mobile app, bookings, invoices and payments."
        updatedAt="Last updated: 19 August 2026"
        languageLinks={[
          { href: "/support?lang=fr", label: "FR", active: false },
          { href: "/support?lang=en", label: "EN", active: true },
        ]}
        footerHref="/login?lang=en"
        footerLabel="Go to client sign in"
        sections={[
          {
            title: "How do I access the Client app?",
            body: [
              "Use the email address attached to your Piano Académie account. The account activation email lets you create your password; the same credentials work on the web portal and in the mobile app.",
              <>
                You can also open the <a href="/login?lang=en">client sign-in page</a> directly.
              </>,
            ],
          },
          {
            title: "Where can I download the app?",
            body: [
              <>
                Download Piano Académie Client from the {externalLink(CLIENT_APP_IOS_URL, "App Store")} or {externalLink(CLIENT_APP_ANDROID_URL, "Google Play")}.
              </>,
              "Booking, payment and account-access emails also include these download links.",
            ],
          },
          {
            title: "What can I do in my client account?",
            body: [
              "You can view upcoming lessons, book eligible slots, manage the relevant family member, check subscriptions and credits, and find invoices, payments and useful school information.",
            ],
          },
          {
            title: "Why is my active pack not accepted for a lesson?",
            body: [
              "An active pack may still be incompatible with the selected lesson type. When this happens, the booking page explains it and offers a compatible plan or one-off payment when available.",
            ],
          },
          {
            title: "I cannot sign in or did not receive the activation email",
            body: [
              "Check your spam folder and make sure you are using the email address registered with the school. You can request a password reset from the sign-in page.",
              <>If the problem continues, email <a href="mailto:contact@piano-academie.com">contact@piano-academie.com</a> or call <a href="tel:+33186476088">+33 1 86 47 60 88</a>.</>,
            ],
          },
          {
            title: "What information should I include in a support request?",
            body: [
              "Include your name, the student concerned, the email used for the account, the app used, and a short description of the problem. For a display issue, include your phone model and iOS or Android version if known.",
            ],
          },
        ]}
      />
    );
  }

  return (
    <PublicInfoPage
      eyebrow="FAQ & assistance"
      title="Aide Piano Académie"
      intro="Retrouvez les réponses concernant votre compte client, l’application mobile, les réservations, les factures et les paiements."
      updatedAt="Dernière mise à jour : 19 août 2026"
      languageLinks={[
        { href: "/support?lang=fr", label: "FR", active: true },
        { href: "/support?lang=en", label: "EN", active: false },
      ]}
      footerHref="/login"
      footerLabel="Accéder à la connexion client"
      sections={[
        {
          title: "Comment accéder à l’application Client ?",
          body: [
            "Utilisez l’adresse e-mail rattachée à votre compte Piano Académie. L’e-mail d’activation vous permet de créer votre mot de passe ; les mêmes identifiants fonctionnent sur le portail web et dans l’application mobile.",
            <>Vous pouvez aussi ouvrir directement la <a href="/login">page de connexion client</a>.</>,
          ],
        },
        {
          title: "Où télécharger l’application ?",
          body: [
            <>
              Téléchargez Piano Académie Client depuis l’{externalLink(CLIENT_APP_IOS_URL, "App Store")} ou {externalLink(CLIENT_APP_ANDROID_URL, "Google Play")}.
            </>,
            "Les e-mails d’accès au compte, de réservation et de paiement contiennent également ces liens de téléchargement.",
          ],
        },
        {
          title: "Que puis-je faire depuis mon espace client ?",
          body: [
            "Vous pouvez consulter les prochains cours, réserver les créneaux éligibles, sélectionner le bon membre de la famille, vérifier les abonnements et crédits, puis retrouver les factures, paiements et informations utiles de l’école.",
          ],
        },
        {
          title: "Pourquoi mon carnet actif n’est-il pas accepté pour un cours ?",
          body: [
            "Un carnet peut être actif sans couvrir le type de cours sélectionné. Dans ce cas, la page de réservation l’indique et propose une formule compatible ou un paiement à l’unité lorsque cette option est disponible.",
          ],
        },
        {
          title: "Je n’arrive pas à me connecter ou je n’ai pas reçu l’e-mail d’activation",
          body: [
            "Vérifiez vos courriers indésirables et assurez-vous d’utiliser l’adresse e-mail enregistrée auprès de l’école. Vous pouvez demander la réinitialisation du mot de passe depuis la page de connexion.",
            <>Si le problème persiste, écrivez à <a href="mailto:contact@piano-academie.com">contact@piano-academie.com</a> ou appelez le <a href="tel:+33186476088">01 86 47 60 88</a>.</>,
          ],
        },
        {
          title: "Quelles informations transmettre au support ?",
          body: [
            "Indiquez votre nom, l’élève concerné, l’adresse e-mail utilisée, l’application concernée et une courte description du problème. Pour un problème d’affichage, ajoutez si possible le modèle du téléphone et la version d’iOS ou d’Android.",
          ],
        },
      ]}
    />
  );
}
