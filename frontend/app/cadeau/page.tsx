import Link from "next/link";
import type { Metadata } from "next";

import PortalBrandLockup from "../../components/portal-brand-lockup";
import { lookupGiftCardAction, redeemGiftCardAction } from "../../lib/actions";
import { getPortalToken } from "../../lib/auth-cookies";
import { backendRequest } from "../../lib/backend";
import { normalizeUiLanguage, type UiLanguage } from "../../lib/ui-i18n";
import type { ClientFamilyOverviewOut, FamilyMemberOut, GiftCardPublicPreviewOut, UserOut } from "../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

export const metadata: Metadata = {
  title: "Carte cadeau | Piano Académie",
  referrer: "no-referrer",
};

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

const copy = {
  fr: {
    title: "J'ai reçu une carte cadeau",
    subtitle: "Activez votre cadeau en quelques instants, puis réservez votre cours.",
    code: "Code de la carte cadeau",
    codeHelp: "Les espaces et les tirets sont acceptés.",
    check: "Vérifier mon cadeau",
    offered: "Votre cadeau",
    for: "Destinataire indiqué :",
    expires: "Code valable jusqu'au",
    loginTitle: "Connectez-vous pour recevoir ce cadeau",
    login: "J'ai déjà un compte",
    signup: "Créer mon compte",
    childSignup: "Créer un compte pour mon enfant",
    accountHelp: "Vous pourrez choisir votre propre compte ou un enfant déjà rattaché avant l'activation.",
    recipient: "À qui attribuer cette offre ?",
    terms: "J'accepte les conditions générales de vente",
    activate: "Activer mon cadeau",
    restart: "Saisir un autre code",
    unavailable: "Cette carte cadeau ne peut pas être activée.",
  },
  en: {
    title: "I received a gift card",
    subtitle: "Activate your gift in a few moments, then book your lesson.",
    code: "Gift card code",
    codeHelp: "Spaces and dashes are accepted.",
    check: "Check my gift",
    offered: "Your gift",
    for: "Named recipient:",
    expires: "Code valid until",
    loginTitle: "Sign in to receive this gift",
    login: "I already have an account",
    signup: "Create my account",
    childSignup: "Create an account for my child",
    accountHelp: "Before activation, you can select your own account or a linked child.",
    recipient: "Who should receive this offer?",
    terms: "I accept the terms and conditions",
    activate: "Activate my gift",
    restart: "Enter another code",
    unavailable: "This gift card cannot be activated.",
  },
} as const;

function memberLabel(member: FamilyMemberOut): string {
  return `${member.first_name ?? ""} ${member.last_name ?? ""}`.trim() || member.email || member.id;
}

function uniqueRecipients(family: ClientFamilyOverviewOut): FamilyMemberOut[] {
  const recipients = [family.me, ...family.links_as_adult.map((link) => link.child)];
  return [...new Map(recipients.filter((member) => member.is_active).map((member) => [member.id, member])).values()];
}

function dateLabel(value: string, language: UiLanguage): string {
  return new Intl.DateTimeFormat(language === "en" ? "en-GB" : "fr-FR", { dateStyle: "long" }).format(new Date(value));
}

export default async function GiftCardPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const params = searchParams ?? {};
  const language = normalizeUiLanguage(readParam(params, "lang"));
  const t = copy[language];
  const giftToken = readParam(params, "gift_token").trim();
  const errorMessage = readParam(params, "error");
  const pageHref = `/cadeau${language === "en" ? "?lang=en" : ""}`;
  const returnTo = giftToken
    ? `${pageHref}${pageHref.includes("?") ? "&" : "?"}gift_token=${encodeURIComponent(giftToken)}`
    : pageHref;

  let preview: GiftCardPublicPreviewOut | null = null;
  let previewError: string | null = null;
  if (giftToken) {
    const previewResult = await backendRequest<GiftCardPublicPreviewOut>(
      `/api/v1/public/gift-cards/context/${encodeURIComponent(giftToken)}`,
    );
    if (previewResult.ok) {
      preview = previewResult.data;
    } else {
      previewError = previewResult.message;
    }
  }

  const portalToken = getPortalToken();
  let me: UserOut | null = null;
  let family: ClientFamilyOverviewOut | null = null;
  if (portalToken && preview) {
    const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, portalToken);
    if (meResult.ok && meResult.data.role === "client") {
      me = meResult.data;
      const familyResult = await backendRequest<ClientFamilyOverviewOut>("/api/v1/clients/me/family", {}, portalToken);
      if (familyResult.ok) {
        family = familyResult.data;
      }
    }
  }
  const recipients = family ? uniqueRecipients(family) : [];

  return (
    <main className="page public-buy-page">
      <section className="public-buy-shell">
        <article className="card public-buy-card">
          <PortalBrandLockup
            title="Piano Académie"
            subtitle={language === "en" ? "Gift card" : "Carte cadeau"}
            tone="light"
            compact
            className="public-buy-brand-lockup"
          />
          <header className="public-buy-header">
            <h1>{t.title}</h1>
            <p className="muted">{t.subtitle}</p>
          </header>

          {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
          {previewError ? <section className="flash-err">{previewError || t.unavailable}</section> : null}

          {!giftToken || previewError ? (
            <form action={lookupGiftCardAction} className="grid public-buy-form">
              <input type="hidden" name="lang" value={language} />
              <label>
                {t.code}
                <input type="text" name="code" required minLength={6} maxLength={80} autoComplete="off" placeholder="XXXX-XXXX-XXXX" />
                <span className="muted">{t.codeHelp}</span>
              </label>
              <button type="submit">{t.check}</button>
            </form>
          ) : null}

          {preview ? (
            <>
              <section className="public-buy-summary">
                <h2>{t.offered}</h2>
                <h3>{preview.plan_name}</h3>
                {preview.plan_description ? <p>{preview.plan_description}</p> : null}
                {preview.recipient_name ? <p><strong>{t.for}</strong> {preview.recipient_name}</p> : null}
                {preview.personal_message ? <blockquote>{preview.personal_message}</blockquote> : null}
                {preview.expires_at ? <p className="muted">{t.expires} {dateLabel(preview.expires_at, language)}.</p> : null}
              </section>

              {!me || !family ? (
                <section className="grid public-buy-form">
                  <h2>{t.loginTitle}</h2>
                  <p className="muted">{t.accountHelp}</p>
                  <Link className="mode-link" href={`/login?mode=login&return_to=${encodeURIComponent(returnTo)}${language === "en" ? "&lang=en" : ""}`}>
                    {t.login}
                  </Link>
                  <Link className="mode-link" href={`/login?mode=signup&return_to=${encodeURIComponent(returnTo)}${language === "en" ? "&lang=en" : ""}`}>
                    {t.signup}
                  </Link>
                  <Link className="mode-link" href={`/login?mode=signup&registration_subject_type=child&return_to=${encodeURIComponent(returnTo)}${language === "en" ? "&lang=en" : ""}`}>
                    {t.childSignup}
                  </Link>
                </section>
              ) : (
                <form action={redeemGiftCardAction} className="grid public-buy-form">
                  <input type="hidden" name="redeem_token" value={preview.redeem_token} />
                  <input type="hidden" name="lang" value={language} />
                  <label>
                    {t.recipient}
                    <select name="user_id" defaultValue={family.me.id} required>
                      {recipients.map((member) => <option key={member.id} value={member.id}>{memberLabel(member)}</option>)}
                    </select>
                  </label>
                  {preview.terms_required ? (
                    <label className="checkbox-line">
                      <input type="checkbox" name="legal_terms_accepted" required />
                      <span>{t.terms} · <Link href={`/cgv?lang=${language}`} target="_blank" rel="noreferrer">CGV</Link></span>
                    </label>
                  ) : null}
                  <button type="submit">{t.activate}</button>
                </form>
              )}
              <p><Link href={pageHref}>{t.restart}</Link></p>
            </>
          ) : null}
        </article>
      </section>
    </main>
  );
}
