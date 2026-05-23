import type { Metadata } from "next";

import { PublicInfoPage } from "../public-info-page";

export const metadata: Metadata = {
  title: "Confidentialite | Piano Academie",
  description: "Information de confidentialite pour les applications Piano Academie.",
};

export default function PrivacyPage(): JSX.Element {
  return (
    <PublicInfoPage
      eyebrow="Confidentialite"
      title="Confidentialite des applications"
      intro="Cette page decrit le cadre general de traitement des donnees pour les espaces client et professeur Piano Academie."
      sections={[
        {
          title: "Donnees traitees",
          body: [
            "Les applications donnent acces aux informations necessaires a la gestion des cours: compte utilisateur, planning, inscriptions, paiements, communications et documents associes.",
            "Les donnees visibles dependent du role connecte: client, responsable legal ou professeur.",
          ],
        },
        {
          title: "Utilisation",
          body: [
            "Les informations sont utilisees pour gerer les reservations, suivre les cours, envoyer les notifications utiles et assurer le fonctionnement administratif de Piano Academie.",
            "Les paiements et certains services techniques peuvent etre traites par des prestataires specialises selon les parcours utilises.",
          ],
        },
        {
          title: "Contact et demandes",
          body: [
            "Pour une demande d'acces, de correction ou de suppression de donnees, contactez l'equipe Piano Academie via les coordonnees habituelles de l'ecole.",
            "Avant soumission publique App Store, cette page doit etre alignee avec la politique de confidentialite complete et les labels App Store Connect.",
          ],
        },
      ]}
    />
  );
}
