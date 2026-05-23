import type { Metadata } from "next";

import { PublicInfoPage } from "../public-info-page";

export const metadata: Metadata = {
  title: "Support | Piano Academie",
  description: "Contact support pour les applications Piano Academie Client et Professeur.",
};

export default function SupportPage(): JSX.Element {
  return (
    <PublicInfoPage
      eyebrow="Support"
      title="Assistance Piano Academie"
      intro="Cette page sert de point de contact public pour les apps mobiles client et professeur."
      sections={[
        {
          title: "Contact",
          body: [
            "Pour toute question liee a votre compte, a vos cours, a un paiement ou a l'utilisation de l'application, contactez l'equipe Piano Academie via les coordonnees habituelles de l'ecole.",
            "Si vous etes deja connecte, privilegiez les messages ou demandes depuis votre espace client ou professeur afin de rattacher la demande au bon dossier.",
          ],
        },
        {
          title: "Informations utiles",
          body: [
            "Indiquez votre nom, le compte concerne, l'app utilisee et une description courte du probleme rencontre.",
            "Pour un probleme d'affichage mobile, ajoutez le modele de telephone et la version iOS lorsque vous les connaissez.",
          ],
        },
      ]}
    />
  );
}
