import type { Metadata } from "next";
import { headers } from "next/headers";

import { PublicInfoPage } from "../public-info-page";

type SearchParams = Record<string, string | string[] | undefined>;
type PrivacyLanguage = "fr" | "en";

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function resolveLanguage(rawLanguage: string, acceptLanguage: string): PrivacyLanguage {
  for (const candidate of [rawLanguage, acceptLanguage]) {
    const normalized = candidate.trim().toLowerCase();
    if (normalized === "en" || normalized.startsWith("en-")) {
      return "en";
    }
    if (normalized === "fr" || normalized.startsWith("fr-")) {
      return "fr";
    }
  }
  return "fr";
}

export function generateMetadata({ searchParams }: { searchParams: SearchParams }): Metadata {
  const language = resolveLanguage(readParam(searchParams, "lang"), headers().get("accept-language") ?? "");
  return {
    title: language === "en" ? "Privacy policy | Piano Académie" : "Politique de confidentialité | Piano Académie",
    description:
      language === "en"
        ? "Privacy policy for the Piano Académie client and teacher services."
        : "Politique de confidentialité des espaces client et professeur Piano Académie.",
    alternates: {
      canonical: "https://app.piano-academie.com/privacy",
      languages: {
        "fr-FR": "https://app.piano-academie.com/privacy?lang=fr",
        "en-GB": "https://app.piano-academie.com/privacy?lang=en",
      },
    },
  };
}

export default function PrivacyPage({ searchParams }: { searchParams: SearchParams }): JSX.Element {
  const language = resolveLanguage(readParam(searchParams, "lang"), headers().get("accept-language") ?? "");

  if (language === "en") {
    return (
      <PublicInfoPage
        eyebrow="Privacy"
        title="Privacy policy"
        intro="This policy explains how Piano Académie handles personal data through its client and teacher portals, mobile applications and related services."
        updatedAt="Effective and last updated: 7 August 2026"
        languageLinks={[
          { href: "/privacy?lang=fr", label: "FR", active: false },
          { href: "/privacy?lang=en", label: "EN", active: true },
        ]}
        footerHref="/login?lang=en"
        footerLabel="Back to sign in"
        sections={[
          {
            title: "1. Who is responsible for your data?",
            body: [
              "The main controller is PIANO ACADEMIE, a French simplified joint-stock company (SAS), SIREN 828 051 417, SIRET 828 051 417 00032, whose registered office is at 1 rue de Richelieu, 75001 Paris, France.",
              "Depending on the service contracted or invoiced, PIANO ACADEMIE SERVICES, a French simplified joint-stock company (SAS), SIREN 828 163 865, SIRET 828 163 865 00011, 19 rue de la Pompe, 75116 Paris, France, may also act as controller.",
              <>
                Privacy contact: <a href="mailto:contact@piano-academie.com">contact@piano-academie.com</a> — telephone: <a href="tel:+33186476088">+33 1 86 47 60 88</a>.
              </>,
            ],
          },
          {
            title: "2. Data we process",
            body: ["Depending on your role and use of the service, we may process the following categories:"],
            items: [
              "identity and contact details: first and last name, date of birth, email address, telephone number, postal address, country, language and time zone;",
              "account, authentication, family, student and legal-representative information, and an optional profile or student photograph;",
              "teaching and operational information: courses, timetables, bookings, attendance, teachers, locations, educational or internal notes, communications and support requests;",
              "commercial and accounting information: offers, subscriptions, packs, credits, purchases, invoices, payment status and masked payment-method information;",
              "technical and security information needed to operate the service, including connection data and, if you enable notifications, an application push token linked to your account.",
            ],
          },
          {
            title: "3. Why and on what legal basis?",
            body: ["We process data only for identified purposes and on the following legal bases:"],
            items: [
              "performance of a contract or pre-contractual steps: creating and administering accounts, courses, bookings, subscriptions, credits, messages and customer support;",
              "legal obligations: invoices, accounting records, tax obligations and responses to competent authorities;",
              "our legitimate interests: securing the service, preventing fraud, maintaining and improving operations, and sending service information where permitted;",
              "your consent where it is specifically required, in particular for optional communications or features. You may withdraw it at any time without affecting earlier lawful processing.",
            ],
          },
          {
            title: "4. Required and optional information",
            body: [
              "Fields marked as required are necessary to create the account, manage the contractual relationship, book a service or meet a legal obligation. If they are not provided, the relevant service may not be available.",
              "Optional information, such as a student photograph, marketing choices and push notifications, can be omitted or disabled without preventing access to the core service.",
            ],
          },
          {
            title: "5. Who receives the data?",
            body: [
              "Access is limited to authorised Piano Académie staff and, only where necessary for their duties, assigned teachers. We also use service providers acting under our instructions or under their own legal responsibilities.",
            ],
            items: [
              "hosting, maintenance, email and SMS delivery providers;",
              "Stripe for eligible adult subscriptions and PayPlug for school and family payments;",
              "Zendesk when you use customer support;",
              "Apple Push Notification service (APNs) when notifications are enabled;",
              "accounting, legal and public authorities where disclosure is required by law.",
              "We do not sell personal data and do not use the applications for advertising tracking.",
            ],
          },
          {
            title: "6. Payments",
            body: [
              "Payment details are entered and secured directly by the relevant payment provider. Piano Académie does not store the full card number or card security code. We retain only the information needed to track the transaction, such as its status, reference, provider and, when available, a masked description of the payment method.",
            ],
          },
          {
            title: "7. International transfers",
            body: [
              "Some technical providers may process data outside the European Economic Area. Where this occurs, the transfer is based on an adequacy decision, the European Commission's Standard Contractual Clauses or another safeguard permitted by data-protection law.",
            ],
          },
          {
            title: "8. How long do we keep data?",
            body: ["We keep personal data only for as long as needed for the relevant purpose:"],
            items: [
              "account and teaching data: for the active contractual relationship, then for the period needed to handle requests and legal claims;",
              "contracts and evidence relating to disputes: generally up to five years after the end of the relationship, subject to applicable suspension or interruption rules;",
              "invoices and accounting records: ten years, as required by French law;",
              "prospect and optional marketing data: up to three years after the last contact or consent, unless you object earlier;",
              "support, security and technical records: only for the operational or security period for which they are needed;",
              "push tokens: until notifications are disabled, the token becomes invalid or the account is deleted.",
            ],
          },
          {
            title: "9. Children and families",
            body: [
              "For a child, the account and required information are supplied or managed by a parent or legal representative. The information is used only for teaching, booking, safety, communication and administration of the school's services.",
            ],
          },
          {
            title: "10. Your rights",
            body: [
              "Subject to the applicable conditions, you may request access, correction, deletion, restriction, objection and portability, and withdraw consent at any time. You may exercise these rights from the relevant account features or by emailing contact@piano-academie.com. We may ask for information needed to verify your identity.",
              <>
                If you believe your rights have not been respected, you may lodge a complaint with the French data-protection authority, the CNIL: <a href="https://www.cnil.fr" rel="noreferrer" target="_blank">www.cnil.fr</a>.
              </>,
            ],
          },
          {
            title: "11. Account deletion and contractual commitments",
            body: [
              "A deletion request can be started from the client account. Deleting an account does not cancel a subscription, a payment obligation or any other commitment to the school. The request may therefore be deferred while an active commitment or an ongoing service requires the account to perform the contract.",
              "Once the applicable commitments have ended and operational requests have been completed, access is disabled and data is deleted or anonymised, except for information that must be retained to comply with accounting, tax, contractual or legal obligations.",
            ],
          },
          {
            title: "12. Cookies, support and notifications",
            body: [
              "The web service uses only the session, authentication, security and preference technologies needed to operate. The Zendesk support widget may use its own technical components when opened. We do not use advertising cookies in the mobile applications.",
              "Push notifications are optional. You can refuse or disable them at any time in your device settings. Disabling them does not prevent service emails required for your bookings, payments or contractual relationship.",
            ],
          },
          {
            title: "13. Security and updates",
            body: [
              "We apply organisational and technical measures appropriate to the nature of the data, including role-based access, secure connections, authentication controls, backups and provider oversight. No system can guarantee absolute security, but suspected incidents are assessed and handled in accordance with applicable law.",
              "This policy may be updated to reflect changes to the service, providers or law. The current version and its effective date are always available on this page.",
            ],
          },
        ]}
      />
    );
  }

  return (
    <PublicInfoPage
      eyebrow="Confidentialité"
      title="Politique de confidentialité"
      intro="Cette politique explique comment Piano Académie traite les données personnelles dans ses espaces client et professeur, ses applications mobiles et les services associés."
      updatedAt="Entrée en vigueur et dernière mise à jour : 7 août 2026"
      languageLinks={[
        { href: "/privacy?lang=fr", label: "FR", active: true },
        { href: "/privacy?lang=en", label: "EN", active: false },
      ]}
      footerHref="/login?lang=fr"
      footerLabel="Retour à la connexion"
      sections={[
        {
          title: "1. Qui est responsable de vos données ?",
          body: [
            "Le responsable principal est PIANO ACADEMIE, société par actions simplifiée (SAS), SIREN 828 051 417, SIRET 828 051 417 00032, dont le siège social est situé 1 rue de Richelieu, 75001 Paris, France.",
            "Selon le service souscrit ou facturé, PIANO ACADEMIE SERVICES, société par actions simplifiée (SAS), SIREN 828 163 865, SIRET 828 163 865 00011, 19 rue de la Pompe, 75116 Paris, France, peut également agir en qualité de responsable du traitement.",
            <>
              Contact confidentialité : <a href="mailto:contact@piano-academie.com">contact@piano-academie.com</a> — téléphone : <a href="tel:+33186476088">01 86 47 60 88</a>.
            </>,
          ],
        },
        {
          title: "2. Données traitées",
          body: ["Selon votre rôle et votre utilisation du service, nous pouvons traiter les catégories suivantes :"],
          items: [
            "identité et coordonnées : nom, prénom, date de naissance, adresse électronique, téléphone, adresse postale, pays, langue et fuseau horaire ;",
            "compte, authentification, liens familiaux, informations sur l'élève et le représentant légal, ainsi qu'une photo de profil ou d'élève facultative ;",
            "informations pédagogiques et opérationnelles : cours, planning, réservations, présences, professeurs, lieux, notes pédagogiques ou internes, communications et demandes d'assistance ;",
            "informations commerciales et comptables : offres, abonnements, carnets, crédits, achats, factures, état des paiements et informations masquées sur le moyen de paiement ;",
            "informations techniques et de sécurité nécessaires au fonctionnement du service, notamment les données de connexion et, si vous activez les notifications, un jeton de notification lié à votre compte.",
          ],
        },
        {
          title: "3. Finalités et bases légales",
          body: ["Nous traitons les données pour des finalités déterminées et sur les bases légales suivantes :"],
          items: [
            "exécution d'un contrat ou mesures précontractuelles : création et administration des comptes, cours, réservations, abonnements, crédits, messages et assistance ;",
            "obligations légales : factures, comptabilité, fiscalité et réponses aux autorités compétentes ;",
            "intérêts légitimes : sécurisation du service, prévention de la fraude, maintenance et amélioration des opérations, et envoi d'informations de service lorsque la loi le permet ;",
            "votre consentement lorsqu'il est expressément requis, notamment pour des communications ou fonctionnalités facultatives. Vous pouvez le retirer à tout moment sans remettre en cause les traitements antérieurs licites.",
          ],
        },
        {
          title: "4. Informations obligatoires et facultatives",
          body: [
            "Les champs indiqués comme obligatoires sont nécessaires pour créer le compte, gérer la relation contractuelle, réserver une prestation ou respecter une obligation légale. Sans ces informations, le service concerné peut ne pas être disponible.",
            "Les informations facultatives, telles qu'une photo d'élève, les choix de communication commerciale et les notifications push, peuvent être omises ou désactivées sans empêcher l'accès au service principal.",
          ],
        },
        {
          title: "5. Destinataires et prestataires",
          body: [
            "L'accès est limité aux collaborateurs autorisés de Piano Académie et, uniquement lorsque leurs missions le nécessitent, aux professeurs assignés. Nous faisons aussi appel à des prestataires agissant selon nos instructions ou sous leurs propres responsabilités légales.",
          ],
          items: [
            "hébergement, maintenance, envoi d'e-mails et de SMS ;",
            "Stripe pour les abonnements adultes éligibles et PayPlug pour les paiements école et famille ;",
            "Zendesk lorsque vous utilisez l'assistance client ;",
            "le service Apple Push Notification (APNs) lorsque les notifications sont activées ;",
            "professionnels de la comptabilité ou du droit et autorités publiques lorsque la loi l'impose.",
            "Nous ne vendons aucune donnée personnelle et n'utilisons pas les applications à des fins de suivi publicitaire.",
          ],
        },
        {
          title: "6. Paiements",
          body: [
            "Les données de paiement sont saisies et sécurisées directement par le prestataire concerné. Piano Académie ne conserve ni le numéro complet de la carte ni son cryptogramme. Nous conservons seulement les informations nécessaires au suivi de la transaction, telles que son état, sa référence, le prestataire et, lorsqu'elle est disponible, une description masquée du moyen de paiement.",
          ],
        },
        {
          title: "7. Transferts internationaux",
          body: [
            "Certains prestataires techniques peuvent traiter des données hors de l'Espace économique européen. Dans ce cas, le transfert repose sur une décision d'adéquation, les clauses contractuelles types de la Commission européenne ou une autre garantie autorisée par la réglementation sur la protection des données.",
          ],
        },
        {
          title: "8. Durées de conservation",
          body: ["Nous conservons les données uniquement pendant la durée nécessaire à chaque finalité :"],
          items: [
            "données de compte et pédagogiques : pendant la relation contractuelle active, puis pendant la durée nécessaire au traitement des demandes et réclamations ;",
            "contrats et preuves utiles en cas de litige : en principe jusqu'à cinq ans après la fin de la relation, sous réserve des règles de suspension ou d'interruption applicables ;",
            "factures et pièces comptables : dix ans conformément au droit français ;",
            "prospects et communication commerciale facultative : jusqu'à trois ans après le dernier contact ou consentement, sauf opposition antérieure ;",
            "assistance, sécurité et traces techniques : uniquement pendant la durée opérationnelle ou de sécurité pour laquelle elles sont nécessaires ;",
            "jetons de notification : jusqu'à la désactivation des notifications, l'invalidation du jeton ou la suppression du compte.",
          ],
        },
        {
          title: "9. Enfants et familles",
          body: [
            "Pour un enfant, le compte et les informations nécessaires sont fournis ou gérés par un parent ou représentant légal. Ces informations servent uniquement à l'enseignement, aux réservations, à la sécurité, aux communications et à l'administration des services de l'école.",
          ],
        },
        {
          title: "10. Vos droits",
          body: [
            "Sous réserve des conditions légales applicables, vous pouvez demander l'accès, la rectification, l'effacement, la limitation, l'opposition et la portabilité de vos données, et retirer votre consentement à tout moment. Vous pouvez exercer ces droits depuis les fonctions prévues dans votre compte ou en écrivant à contact@piano-academie.com. Nous pouvons demander les informations nécessaires pour vérifier votre identité.",
            <>
              Si vous estimez que vos droits ne sont pas respectés, vous pouvez saisir la Commission nationale de l'informatique et des libertés (CNIL) : <a href="https://www.cnil.fr" rel="noreferrer" target="_blank">www.cnil.fr</a>.
            </>,
          ],
        },
        {
          title: "11. Suppression du compte et engagements contractuels",
          body: [
            "Une demande de suppression peut être initiée depuis le compte client. La suppression du compte ne résilie pas un abonnement, une obligation de paiement ou un autre engagement envers l'école. Elle peut donc être différée tant qu'un engagement actif ou une prestation en cours nécessite le maintien du compte pour exécuter le contrat.",
            "Une fois les engagements concernés terminés et les demandes opérationnelles traitées, l'accès est désactivé et les données sont supprimées ou anonymisées, à l'exception des informations qui doivent être conservées pour respecter les obligations comptables, fiscales, contractuelles ou légales.",
          ],
        },
        {
          title: "12. Cookies, assistance et notifications",
          body: [
            "Le service web utilise uniquement les technologies de session, d'authentification, de sécurité et de préférence nécessaires à son fonctionnement. Le widget d'assistance Zendesk peut utiliser ses propres composants techniques lorsqu'il est ouvert. Nous n'utilisons pas de cookies publicitaires dans les applications mobiles.",
            "Les notifications push sont facultatives. Vous pouvez les refuser ou les désactiver à tout moment dans les réglages de votre appareil. Leur désactivation n'empêche pas l'envoi des e-mails de service nécessaires à vos réservations, paiements ou à la relation contractuelle.",
          ],
        },
        {
          title: "13. Sécurité et mises à jour",
          body: [
            "Nous appliquons des mesures organisationnelles et techniques adaptées à la nature des données, notamment des droits d'accès par rôle, des connexions sécurisées, des contrôles d'authentification, des sauvegardes et un suivi des prestataires. Aucun système ne peut garantir une sécurité absolue, mais les incidents suspectés sont évalués et traités conformément au droit applicable.",
            "Cette politique peut évoluer afin de refléter les changements du service, des prestataires ou de la réglementation. La version en vigueur et sa date d'application restent disponibles sur cette page.",
          ],
        },
      ]}
    />
  );
}
