"use client";

import { useEffect, useState } from "react";
import Image from "next/image";

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
};

type InstallState = "checking" | "available" | "instructions" | "installed";

type AppInstallCardProps = {
  language: "fr" | "en";
};

type AppInstallMenuLinkProps = AppInstallCardProps & {
  href: string;
};

const copy = {
  fr: {
    eyebrow: "APPLICATION PROFESSEUR",
    title: "Installer Piano Academie Professeur",
    description: "Accédez à votre planning, aux présences, aux messages et à vos relevés depuis une icône sur votre téléphone.",
    install: "Installer l’application",
    installed: "Application installée",
    installedHelp: "Ouvrez-la depuis l’icône Piano Academie sur votre écran d’accueil.",
    ios: "Sur iPhone ou iPad : touchez Partager dans Safari, puis « Sur l’écran d’accueil » et enfin « Ajouter ».",
    android: "Sur Android : ouvrez le menu du navigateur, puis choisissez « Installer l’application » ou « Ajouter à l’écran d’accueil ».",
    desktop: "Sur ordinateur : utilisez l’icône d’installation située à droite de la barre d’adresse de Chrome ou Edge.",
    secure: "Votre connexion reste protégée et utilise le même compte professeur que le portail.",
  },
  en: {
    eyebrow: "TEACHER APP",
    title: "Install Piano Academie Teacher",
    description: "Open your schedule, attendance, messages and statements from an icon on your phone.",
    install: "Install the app",
    installed: "App installed",
    installedHelp: "Open it from the Piano Academie icon on your Home Screen.",
    ios: "On iPhone or iPad: tap Share in Safari, then “Add to Home Screen”, and finally “Add”.",
    android: "On Android: open the browser menu, then select “Install app” or “Add to Home screen”.",
    desktop: "On a computer: use the install icon on the right-hand side of the Chrome or Edge address bar.",
    secure: "Your connection remains protected and uses the same teacher account as the portal.",
  },
} as const;

function isStandalone(): boolean {
  const navigatorWithStandalone = navigator as Navigator & { standalone?: boolean };
  const windowWithCapacitor = window as Window & { Capacitor?: { isNativePlatform?: () => boolean } };
  return (
    window.matchMedia("(display-mode: standalone)").matches
    || navigatorWithStandalone.standalone === true
    || windowWithCapacitor.Capacitor?.isNativePlatform?.() === true
  );
}

export function AppInstallMenuLink({ language, href }: AppInstallMenuLinkProps): JSX.Element | null {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setVisible(!isStandalone());
  }, []);

  if (!visible) {
    return null;
  }

  return (
    <a className="teacher-header-menu-link" href={href}>
      {language === "en" ? "Install the app" : "Installer l’application"}
    </a>
  );
}

export default function AppInstallCard({ language }: AppInstallCardProps): JSX.Element {
  const text = copy[language];
  const [installState, setInstallState] = useState<InstallState>("checking");
  const [installPrompt, setInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [platform, setPlatform] = useState<"ios" | "android" | "desktop">("desktop");
  const [showInstructions, setShowInstructions] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const userAgent = navigator.userAgent.toLowerCase();
    const appleMobile = /iphone|ipad|ipod/.test(userAgent);
    const android = /android/.test(userAgent);
    setPlatform(appleMobile ? "ios" : android ? "android" : "desktop");

    const standalone = isStandalone();
    setVisible(!standalone);
    if (standalone) {
      setInstallState("installed");
    } else {
      setInstallState("instructions");
    }

    if ("serviceWorker" in navigator) {
      void navigator.serviceWorker.register("/prof-sw.js", { scope: "/" }).catch(() => undefined);
    }

    const onBeforeInstallPrompt = (event: Event) => {
      event.preventDefault();
      setInstallPrompt(event as BeforeInstallPromptEvent);
      setInstallState("available");
    };
    const onInstalled = () => {
      setInstallPrompt(null);
      setInstallState("installed");
      setShowInstructions(false);
    };

    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  const install = async () => {
    if (!installPrompt) {
      setShowInstructions(true);
      return;
    }
    await installPrompt.prompt();
    const choice = await installPrompt.userChoice;
    if (choice.outcome === "accepted") {
      setInstallPrompt(null);
    }
  };

  const platformInstructions = platform === "ios" ? text.ios : platform === "android" ? text.android : text.desktop;

  if (!visible) {
    return <></>;
  }

  return (
    <section id="prof-mobile-app" className="teacher-mobile-app-card card" aria-labelledby="prof-mobile-app-title">
      <div className="teacher-mobile-app-icon" aria-hidden="true">
        <Image src="/app-icons/piano-academie-192.png" alt="" width={64} height={64} />
      </div>
      <div className="teacher-mobile-app-content">
        <small className="teacher-mobile-app-eyebrow">{text.eyebrow}</small>
        <h2 id="prof-mobile-app-title">{text.title}</h2>
        <p>{text.description}</p>

        {installState === "installed" ? (
          <div className="teacher-mobile-app-installed" role="status">
            <strong>✓ {text.installed}</strong>
            <span>{text.installedHelp}</span>
          </div>
        ) : (
          <button
            className="primary teacher-mobile-app-button"
            type="button"
            onClick={install}
            disabled={installState === "checking"}
          >
            {text.install}
          </button>
        )}

        {showInstructions && installState !== "installed" ? (
          <div className="teacher-mobile-app-instructions" role="status">
            {platformInstructions}
          </div>
        ) : null}
        <small className="muted">{text.secure}</small>
      </div>
    </section>
  );
}
