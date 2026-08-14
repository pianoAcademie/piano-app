# Publics et quota adulte par créneau

Chaque créneau conserve une capacité totale (`capacity_max`) et peut désormais définir indépendamment :

- si les réservations enfant sont ouvertes ;
- si les réservations adulte sont ouvertes ;
- un plafond adulte facultatif compris dans la capacité totale ;
- si les essais enfant et adulte sont autorisés.

Le plafond adulte est **non réservé**. Pour une capacité totale de 6 et un plafond adulte de 2, les combinaisons de 6 enfants ou de 4 enfants et 2 adultes sont toutes deux possibles. En revanche, un troisième adulte est placé en liste d’attente même lorsqu’une place globale reste disponible pour un enfant.

Les réservations `BOOKED` et `PENDING_PAYMENT` consomment la capacité totale et le quota correspondant. Un essai adulte consomme également une place du quota adulte. Lors d’une promotion de liste d’attente, un adulte bloqué par son quota ne bloque pas la promotion d’un enfant situé après lui.

Les règles sont éditées depuis la fiche du créneau. La portée standard du planning s’applique : occurrence seule, occurrences futures ou série complète.
