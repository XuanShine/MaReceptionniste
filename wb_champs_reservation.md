# WuBook Wired — champs d'une réservation (fetch_booking / fetch_bookings)

Source : 5 092 réservations en cache (`wb_cache.json`, créées du 29/10/2024 au 19/11/2026, récupérées via `fetch_bookings`), et la doc officielle https://tdocs.wubook.net/wired/fetch.html. Aucun appel API pour ce document.

Noms des champs = clés EXACTES renvoyées par l'API. `[]` = élément d'une liste, `.` = sous-champ, `<room_id>` = clé variable (id du type de chambre).

Fiabilité : **documenté** = décrit dans la doc WuBook ; **documenté + précisé** = doc + vérifié/complété sur nos données ; **déduit, non documenté** = la doc ne dit rien, sens tiré des données.

Colonne « Données » : type · % des réservations où le champ existe · % où il est non vide/non nul · nombre de valeurs distinctes. Pour les champs à peu de valeurs, la répartition complète est donnée entre parenthèses (nombre d'occurrences). Les données personnelles sont anonymisées.


## 1. Identifiants & statut

| Champ | Sens | Exemple / valeurs | Données | Fiabilité |
|---|---|---|---|---|
| `reservation_code` | Identifiant unique WuBook de la réservation (« rcode »). C'est aussi l'horodatage Unix de création : converti en heure de Paris il donne exactement date_received_time (vérifié sur les 5 092). | 1793181697 | entier · présent 100.0 % · rempli 100.0 % · 5092 val. | documenté + précisé par les données |
| `status` | Statut : 1 = confirmée ; 2 = en attente d'acceptation (site/réception en ligne) ; 3 = refusée (site) ; 4 = acceptée (site, compte comme confirmée) ; 5 = annulée ; 6 = annulée avec pénalité (doc : « probablement plus utilisé », jamais vu ici). Aucun statut « modifiée » n'existe. | 1 (4238), 5 (812), 3 (23), 4 (10), 2 (9) | entier · présent 100.0 % · rempli 100.0 % · 5 val. | documenté |
| `status_reason` | Raison/commentaire lié au statut. Vu ici : « Confirmed with Payment (amount: X) » (site payé en ligne), « Deleted by Payment Gateway response » (refus paiement), « Unknown reason » (annulations Expedia/site), « Réservation acceptée automatiquement », ou recopie de la note Booking sur les annulations. | « Confirmed with Payment (amount: 120.0) », « Unknown reason », « Deleted by Payment Gateway response », « Réservation acceptée automatiquement », texte de note Booking recopié | texte · présent 100.0 % · rempli 21.6 % · 691 val. | documenté + précisé par les données |
| `was_modified` | 1 = cette réservation a été annulée parce qu'elle a été REMPLACÉE par une modification (status=5 dans ce cas). 0 sinon. | 0 (4975), 1 (117) | entier · présent 100.0 % · rempli 2.3 % · 2 val. | documenté |
| `modified_reservations` | Chaîne de modification (liste de rcode). Sur la nouvelle réservation : le rcode qu'elle remplace. Sur l'ancienne (was_modified=1) : son propre rcode, ou le rcode d'origine de la chaîne si elle était déjà une modification. Vide si jamais modifiée. | [1791733319] | liste · présent 100.0 % · rempli 4.2 % · 0 val. | documenté |
| `modified_reservations[]` | Un rcode WuBook de la chaîne de modification. | 1791733319 | entier · présent 4.2 % · rempli 4.2 % · 119 val. | documenté |
| `amount_reason` | Commentaire saisi quand le montant a été modifié dans l'extranet. Toujours vide ici. | "" (5092) | texte · présent 100.0 % · rempli 0.0 % · 1 val. | documenté |
| `sessionSeed` | Étiquette sessionSeed éventuellement passée à l'ouverture du moteur de réservation (WooDoo Online Reception). Toujours vide ici. | "" (5092) | texte · présent 100.0 % · rempli 0.0 % · 1 val. | documenté |
| `origin_company_name` | Paramètre « origin » passé lors d'une création via new_reservation (API). Toujours vide ici. | "" (5092) | texte · présent 100.0 % · rempli 0.0 % · 1 val. | documenté |

## 2. Dates

| Champ | Sens | Exemple / valeurs | Données | Fiabilité |
|---|---|---|---|---|
| `date_received_time` | Date et heure de création de la réservation, format « JJ/MM/AAAA HH:MM:SS », heure de Paris. | "28/10/2026 11:01:37" | texte · présent 100.0 % · rempli 100.0 % · 5092 val. | documenté |
| `date_received` | Date de création seule (JJ/MM/AAAA). Obsolète, remplacée par date_received_time (toujours identique à sa partie date). | "27/08/2026", "05/10/2026", "17/07/2026" | texte · présent 100.0 % · rempli 100.0 % · 509 val. | documenté |
| `date_arrival` | Date d'arrivée (JJ/MM/AAAA). | "12/10/2026", "05/09/2026", "15/09/2026" | texte · présent 100.0 % · rempli 100.0 % · 519 val. | documenté |
| `date_departure` | Date de départ (JJ/MM/AAAA). La nuit du départ n'est PAS facturée : nuits = départ − arrivée. | "18/09/2026", "30/08/2026", "27/08/2026" | texte · présent 100.0 % · rempli 100.0 % · 527 val. | documenté |
| `arrival_hour` | Heure d'arrivée annoncée par le client (« HH:MM »), « -- » si inconnue (toujours « -- » pour Booking/Expedia/canal 43), parfois vide en saisie manuelle. La doc ne décrit pas la valeur. | "--", "14:00", "10:00" | texte · présent 100.0 % · rempli 99.8 % · 43 val. | déduit, non documenté |

## 3. Canal & origine

| Champ | Sens | Exemple / valeurs | Données | Fiabilité |
|---|---|---|---|---|
| `id_channel` | Type de canal OTA (tableau get_channels_info). Ici : 0 = pas d'OTA (site, saisie manuelle, Google, Alien…) ; 1 = Expedia ; 2 = Booking.com ; 43 = canal dont les codes commencent par « HM » et qui facture des « PASS_THROUGH_CLEANING_FEE » → très probablement Airbnb (non vérifié par get_channels_info). | 2 (2798), 0 (1754), 1 (522), 43 (18) | entier · présent 100.0 % · rempli 65.6 % · 4 val. | documenté + précisé par les données |
| `id_woodoo` | Identifiant du canal WooDoo connecté pour cet hôtel (vide si pas d'OTA). Ici : 129782 = Booking, 140111 = Expedia, 140029 = canal 43. Type texte vide ou entier. | 129782 (2798), "" (1754), 140111 (522), 140029 (18) | texte/entier · présent 100.0 % · rempli 65.6 % · 4 val. | documenté + précisé par les données |
| `channel_reservation_code` | Numéro de réservation chez l'OTA (n° Booking, n° Expedia, code « HM… » pour le canal 43). Vide si pas d'OTA. | "5052128670" (Booking/Expedia), "HM…" (canal 43) | texte · présent 100.0 % · rempli 65.6 % · 3224 val. | documenté |
| `fount` | Identifiant de la source « Fount » quand id_channel=0. Valeurs vues : 1946abbf… = YouBook (saisie manuelle : téléphone, comptoir, mail confondus) ; wowowowo… = WooDoo Online Reception (le moteur du site) ; 4ecadd50… = Google Free Booking Link ; f41t2217… = Alien. Vide pour les OTA. | "" (3338), "1946abbfb5d94fb6961da5eb657408e3" (955), "wowowowowowwowowowowowowwowowowo" (727), "4ecadd502b4eecea08aba6b3ef74dc72" (60), "f41t22170134e2dc176c3c4eehb5ab4a" (12) | texte · présent 100.0 % · rempli 34.4 % · 5 val. | documenté + précisé par les données |
| `device` | Appareil utilisé (moteur du site uniquement) : -1 non détectable, 0 inconnu, 1 mobile, 2 tablette, 3 ordinateur, 4 iPhone, 5 iPad, 6 Android, 7 BlackBerry, 8 iPod. Toujours -1 hors site/Google. | -1 (4305), 3 (435), 1 (191), 4 (153), 5 (5), 2 (3) | entier · présent 100.0 % · rempli 100.0 % · 6 val. | documenté |
| `channel_data` | Infos normalisées pour tous les canaux. Vide pour site, manuel, Google, Alien. | (structure) | objet · présent 100.0 % · rempli 65.6 % · 0 val. | documenté |
| `channel_data.pay_model` | Modèle de paiement : « merchant » = le client paie l'OTA qui reverse à l'hôtel ; « agency » = le client paie l'hôtel qui paie la commission. Ici toujours « merchant ». (La doc l'écrit « paymodel », la clé réelle est pay_model.) | "merchant" (3338) | texte · présent 65.6 % · rempli 65.6 % · 1 val. | documenté + précisé par les données |
| `channel_data.vat_included` | 1 = la TVA est incluse dans le montant ; 0 = non. | 1 (3318), 0 (2) | entier · présent 65.2 % · rempli 65.2 % · 2 val. | documenté |
| `channel_data.addons_embedded` | true = les suppléments (addons) sont inclus dans amount. true seulement pour le canal 43 (frais de ménage inclus). | false (3320), true (18) | booléen · présent 65.6 % · rempli 0.4 % · 2 val. | documenté + précisé par les données |
| `channel_data.vcc_additional_info` | Infos sur la carte virtuelle (VCC) de l'OTA (Booking ici). Absent quand pas de VCC. | (structure) | objet · présent 27.4 % · rempli 27.4 % · 0 val. | documenté |
| `channel_data.vcc_additional_info.vcc_valid_from` | Début de validité de la carte virtuelle (horodatage Unix, minuit heure de Paris). | 1758751200 (= 25/09/2025 00:00, heure de Paris) | entier · présent 27.4 % · rempli 27.4 % · 363 val. | documenté + précisé par les données |
| `channel_data.vcc_additional_info.vcc_valid_til` | Fin de validité de la carte virtuelle (horodatage Unix). | 1817071200 (= 01/08/2027 00:00, heure de Paris) | entier · présent 27.4 % · rempli 27.4 % · 14 val. | documenté + précisé par les données |
| `channel_data.vcc_additional_info.vcc_balance` | Montant disponible sur la carte virtuelle. | 43.63, 47.51, 66.82 | décimal · présent 27.4 % · rempli 27.4 % · 1092 val. | documenté |
| `channel_data.vcc_additional_info.vcc_currency_code` | Devise de la carte virtuelle. | "EUR" (1395) | texte · présent 27.4 % · rempli 27.4 % · 1 val. | documenté |
| `channel_data.split_reservation` | (Documenté mais jamais présent ici) n_stream / tot_stream : partie d'une réservation éclatée. | — | jamais présent | documenté |

## 4. Client

| Champ | Sens | Exemple / valeurs | Données | Fiabilité |
|---|---|---|---|---|
| `customer_name` | Prénom du client. | texte (prénom du client) | texte · présent 100.0 % · rempli 100.0 % · 2986 val. | documenté |
| `customer_surname` | Nom du client. | texte (nom du client) | texte · présent 100.0 % · rempli 100.0 % · 4291 val. | documenté |
| `customer_mail` | E-mail (adresse relais OTA pour Booking/Expedia). | texte (e-mail du client) | texte · présent 100.0 % · rempli 100.0 % · 4549 val. | déduit, non documenté |
| `customer_phone` | Téléphone (souvent masqué par les OTA). | texte (téléphone du client) | texte · présent 100.0 % · rempli 92.4 % · 3797 val. | déduit, non documenté |
| `customer_address` | Adresse postale. | texte (adresse postale) | texte · présent 100.0 % · rempli 6.1 % · 153 val. | documenté |
| `customer_city` | Ville. | texte (ville) | texte · présent 100.0 % · rempli 31.1 % · 125 val. | documenté |
| `customer_zip` | Code postal. | texte (code postal) | texte · présent 100.0 % · rempli 3.8 % · 50 val. | documenté |
| `customer_country` | Pays, code ISO à 2 lettres ; « -- » si inconnu. | "FR", "--", "IT" | texte · présent 100.0 % · rempli 100.0 % · 85 val. | déduit, non documenté |
| `customer_language` | Langue sous forme de code numérique (puissance de 2) : 1 it, 2 en, 4 fr, 8 de, 16 pt, 32 es, 34 hu, 64 th, 128 ru, 256 nl, 512 gr, 2048 cs, 4096 hr, 8192 ro, 131072 uk, 262144 ca, 524288 sv, 4194304 br, 8388608 zh, 16777216 pl, 536870912 tr. Correspondance déduite en croisant avec customer_language_iso. | 4, 2, 1 | entier · présent 100.0 % · rempli 100.0 % · 21 val. | déduit, non documenté |
| `customer_language_iso` | Langue du client, code ISO 639-1 (fr, en, it…). | "fr", "en", "it" | texte · présent 100.0 % · rempli 100.0 % · 21 val. | documenté |
| `customer_notes` | Remarques : demandes du client et textes automatiques des OTA (carte virtuelle, prépayé, lits…). Pour la saisie manuelle : note interne (ex. « devis »). | texte libre, ex. « Vous avez reçu une carte de crédit virtuelle… » (Booking), « 1 Queen Bed. Non-Smoking. Virtual card will be activated… » (Expedia), « devis » (manuel) | texte · présent 100.0 % · rempli 74.7 % · 2680 val. | documenté + précisé par les données |
| `men` | Nombre d'adultes (-1 si non défini, jamais vu ici). | 2, 1, 3 | entier · présent 100.0 % · rempli 100.0 % · 27 val. | documenté |
| `children` | Nombre d'enfants. | 0 (4762), 1 (218), 2 (95), 3 (12), 4 (4), 7 (1) | entier · présent 100.0 % · rempli 6.5 % · 6 val. | documenté |
| `rooms_occupancies` | Une entrée par chambre réservée : nombre de personnes dans la chambre. | (structure) | liste · présent 100.0 % · rempli 100.0 % · 0 val. | documenté |
| `rooms_occupancies[].id` | Identifiant WuBook du type de chambre. | 329039, 405127, 329667 | entier · présent 100.0 % · rempli 100.0 % · 15 val. | documenté |
| `rooms_occupancies[].occupancy` | Nombre de personnes dans cette chambre. La somme = men + children dans 98 % des cas. | 2 (2926), 1 (2427), 3 (571), 4 (133) | entier · présent 100.0 % · rempli 100.0 % · 4 val. | documenté + précisé par les données |

## 5. Chambres & prix

| Champ | Sens | Exemple / valeurs | Données | Fiabilité |
|---|---|---|---|---|
| `amount` | Montant de la réservation. Selon le canal (vérifié sur les réservations confirmées) : Booking/Expedia = somme des nuits (TVA incluse, taxe de séjour EXCLUE) ; site/Google = nuits + extras (petit-déjeuner, parking…) hors taxe de séjour ; manuel (YouBook) = prix final saisi (nuits + extras, ou prix forcé/remisé) ; canal 43 = nuits + frais de ménage. Peut être modifié dans l'extranet. | 43.63, 53.18, 87.3 | décimal · présent 100.0 % · rempli 100.0 % · 3876 val. | documenté + précisé par les données |
| `orig_amount` | Montant d'origine, avant une éventuelle modification de amount dans l'extranet (différent de amount sur 2 réservations manuelles seulement). | 43.63, 53.18, 87.3 | décimal · présent 100.0 % · rempli 100.0 % · 3877 val. | documenté |
| `currency` | Devise (EUR). | "EUR" (5092) | texte · présent 100.0 % · rempli 100.0 % · 1 val. | documenté |
| `city_tax` | Taxe de séjour calculée par WuBook selon la règle de l'hôtel, NON incluse dans amount. Remplie seulement pour site, manuel, Google, Alien ; 0 pour les OTA (pour Booking elle est dans addons_list). | 4.0, 2.0, 8.0 | décimal · présent 100.0 % · rempli 34.4 % · 44 val. | documenté + précisé par les données |
| `rooms` | Liste des identifiants de types de chambre réservés, séparés par des virgules (un id répété = plusieurs chambres du même type). | "329039", "405127", "329667" | texte · présent 100.0 % · rempli 100.0 % · 148 val. | documenté |
| `roomnight` | « Nuitées » selon WuBook ; la doc dit « presque inutile ». En pratique = nuits × adultes dans ~80 % des cas, ce n'est PAS le nombre de chambres-nuits. Ne pas l'utiliser. | 2, 1, 4 | entier · présent 100.0 % · rempli 100.0 % · 44 val. | documenté + précisé par les données |
| `booked_rooms` | Détail par chambre réservée et par nuit — la source fiable pour compter les nuits et le CA hébergement. | (structure) | liste · présent 100.0 % · rempli 100.0 % · 0 val. | documenté |
| `booked_rooms[].room_id` | Identifiant WuBook du type de chambre. | 329039, 405127, 329667 | entier · présent 100.0 % · rempli 100.0 % · 15 val. | documenté |
| `booked_rooms[].roomdays` | Une ligne par nuit pour cette chambre. | (structure) | liste · présent 100.0 % · rempli 100.0 % · 0 val. | documenté |
| `booked_rooms[].roomdays[].day` | Date de la nuit (JJ/MM/AAAA). | "08/09/2026", "29/09/2026", "26/05/2026" | texte · présent 100.0 % · rempli 100.0 % · 605 val. | documenté |
| `booked_rooms[].roomdays[].price` | Prix de la nuit pour cette chambre (arrondi à 2 décimales). Hors extras. Pour les saisies manuelles avec remise/prix forcé, c'est le prix AVANT remise. | 64.0, 57.6, 69.0 | décimal · présent 100.0 % · rempli 100.0 % · 4530 val. | documenté + précisé par les données |
| `booked_rooms[].roomdays[].rate_id` | Plan tarifaire réservé : <0 inconnu, 0 = tarif standard WuBook (parité), >0 = id du plan. Vus : 185704 (Booking « Standard Rate » et canal 43), 231174 (Booking « Double Petit-déjeuner inclus »), 231176 (Booking triple PDJ), 231173 (Booking « NR 7 nuits »), 231258/231259/231260 (Expedia), 231177 (site, plan lié à l'offre « Prix Spécial Site Web »). | 185704 (4115), 0 (4041), 231174 (1752), 231258 (970), 231177 (837), 231259 (395), 231176 (67), 231260 (32), 231173 (11) | entier · présent 100.0 % · rempli 73.3 % · 9 val. | documenté + précisé par les données |
| `booked_rooms[].roomdays[].board_code` | Pension de la nuit : « nb » = sans repas, « bb » = petit-déjeuner. Présent pour Booking/Expedia uniquement. | "nb" (5100), "bb" (2246) | texte · présent 65.2 % · rempli 65.2 % · 2 val. | déduit, non documenté |
| `booked_rooms[].ancillary` | Infos non standard propres au canal, niveau chambre. Vide pour site/manuel/Google/Alien/43. Documenté : « auto_generated: True » si WuBook a reconstruit le détail par jour (jamais vu ici). | (structure) | objet · présent 99.6 % · rempli 65.2 % · 0 val. | documenté |
| `booked_rooms[].roomdays[].ancillary` | Infos non standard propres au canal, niveau nuit. | (structure) | objet · présent 99.6 % · rempli 65.2 % · 0 val. | documenté |
| `dayprices` | Prix par jour, par TYPE de chambre (clé = id du type). Doc : obsolète pour les OTA. Piège : plusieurs chambres du même type sont fusionnées/écrasées → ne pas utiliser pour compter. | (structure) | objet · présent 100.0 % · rempli 100.0 % · 0 val. | documenté + précisé par les données |
| `dayprices.<room_id>` | Liste des prix par nuit pour ce type de chambre (non arrondis, ex. 77.855). | (structure) | liste · présent 100.0 % · rempli 100.0 % · 0 val. | documenté + précisé par les données |
| `dayprices.<room_id>[]` | Un prix de nuit. | 69.0, 50.0, 43.65 | décimal · présent 100.0 % · rempli 100.0 % · 4929 val. | documenté + précisé par les données |
| `forced_price` | 1 = prix forcé : ignorer dayprices (saisies manuelles et Alien). Absent sinon. | 1 (22) | entier · présent 0.4 % · rempli 0.4 % · 1 val. | documenté |
| `booked_rate` | Obsolète (voir booked_rooms[].roomdays[].rate_id) : plan tarifaire réservé, -1 inconnu, 0 standard. | 185704 (1932), 0 (1360), 231174 (849), 231177 (400), 231258 (320), 231259 (168), 231176 (46), 231260 (10), 231173 (7) | entier · présent 100.0 % · rempli 73.3 % · 9 val. | documenté |
| `boards` | Pension choisie sur le moteur WuBook, par type de chambre (clé = id). Objet pour site/manuel/Google/Alien, texte vide pour les OTA. | "" (3345) | objet/texte · présent 100.0 % · rempli 34.3 % · 1 val. | documenté |
| `boards.<room_id>` | Code pension : « nb » sans repas, « bb » petit-déjeuner (doc cite aussi « fb » pension complète). | "nb" (1880), "bb" (2) | texte · présent 34.3 % · rempli 34.3 % · 2 val. | documenté + précisé par les données |
| `tboard` | Montant total des repas (pensions) sur tout le séjour. Presque toujours 0 (le petit-déjeuner est vendu en extra). | 0.0 (5090), 16.0 (1), 8.0 (1) | décimal · présent 100.0 % · rempli 0.0 % · 3 val. | documenté |
| `addons_list` | Suppléments. Pour les OTA : {name, req, price}. Pour le site/manuel : {id, name, number, perday, price}. | (structure) | liste · présent 100.0 % · rempli 73.1 % · 0 val. | documenté |
| `addons_list[].name` | Nom du supplément : « taxe de séjour » (Booking), « Petit-Déjeuner Continental (total) », « Parking », « Voiture », « Animal », « Plateau D'accueil », « Mini-Frigo », « Lit Bébé », « PASS_THROUGH_CLEANING_FEE »/« PASS_THROUGH_PET_FEE » (canal 43). | "taxe de séjour" (3125), "Petit-Déjeuner Continental (total)" (667), "Parking" (379), "Petit-déjeuner (total)" (72), "Animal" (48), "Voiture" (42), "Plateau D’accueil" (36), "Mini-Frigo" (26), "PASS_THROUGH_CLEANING_FEE" (18), "Lit Bébé" (8), "PASS_THROUGH_PET_FEE" (1) | texte · présent 73.1 % · rempli 73.1 % · 11 val. | documenté |
| `addons_list[].price` | OTA : prix UNITAIRE. Site/manuel : prix TOTAL de la ligne. | 3.0, 2.0, 10.0 | décimal · présent 73.1 % · rempli 73.1 % · 39 val. | documenté |
| `addons_list[].req` | OTA : quantité. Pour la taxe de séjour Booking = personnes × nuits (prix 3 € etc.). | 2, 1, 4 | entier · présent 54.9 % · rempli 54.9 % · 29 val. | documenté + précisé par les données |
| `addons_list[].id` | Site/manuel : id de l'« opportunité » (extra) WuBook. 25344 = petit-déjeuner, 31344 = parking (ancien nom « Voiture »), 25635 = animal, 31373 = plateau d'accueil, 31371 = mini-frigo, 31370 = lit bébé. | 25344 (739), 31344 (421), 25635 (48), 31373 (36), 31371 (26), 31370 (8) | entier · présent 18.2 % · rempli 18.2 % · 6 val. | documenté + précisé par les données |
| `addons_list[].number` | Site/manuel : quantité demandée. | 1, 2, 3 | entier · présent 18.2 % · rempli 18.2 % · 24 val. | documenté |
| `addons_list[].perday` | Site/manuel : 1 = prix par jour, 0 = prix global. | 0 (774), 1 (504) | entier · présent 18.2 % · rempli 9.5 % · 2 val. | documenté |
| `addons_list[].id_room` | (Documenté, jamais présent ici) chambre concernée par l'extra. | — | jamais présent | documenté |
| `opportunities` | Nombre d'extras « génériques » dans addons_list (moteur WuBook). | 0 (4165), 1 (600), 2 (306), 3 (20), 6 (1) | entier · présent 100.0 % · rempli 18.2 % · 5 val. | documenté |
| `room_opportunities` | Nombre d'extras liés à une chambre (toujours 0 ici). | 0 (5092) | entier · présent 100.0 % · rempli 0.0 % · 1 val. | documenté |
| `special_offer` | Offre spéciale du moteur WuBook appliquée (objet) ; texte vide sinon. | "" (4692) | texte/objet · présent 100.0 % · rempli 7.9 % · 1 val. | documenté |
| `special_offer.id` | Id de l'offre (65034). | 65034 (400) | entier · présent 7.9 % · rempli 7.9 % · 1 val. | documenté |
| `special_offer.name` | Nom de l'offre (« Prix Spécial Site Web », ancien nom « Site Web »). | "Prix Spécial Site Web" (322), "Site Web" (78) | texte · présent 7.9 % · rempli 7.9 % · 2 val. | documenté + précisé par les données |
| `special_offer.type` | Type : 1 pourcentage, 2 fixe, -1 liée à un plan tarifaire (toujours -1 ici). | -1 (400) | entier · présent 7.9 % · rempli 7.9 % · 1 val. | documenté |
| `special_offer.value` | Valeur de remise si type 1 ou 2, sinon -1. | -1 (400) | entier · présent 7.9 % · rempli 7.9 % · 1 val. | documenté |
| `special_offer.pricing_plan` | Plan tarifaire lié si type -1 (231177), sinon -1. | 231177 (400) | entier · présent 7.9 % · rempli 7.9 % · 1 val. | documenté |
| `special_offer.discount` | Montant remisé en € par l'offre. | 1.3500000000000014, 2.700000000000003, 1.5300000000000011 | décimal · présent 7.9 % · rempli 7.9 % · 323 val. | documenté |
| `discount` | Remise appliquée (code promo / remise manuelle). Présent sur 49 résas (manuel et Alien), dont 22 objets vides. | (structure) | objet · présent 1.0 % · rempli 0.5 % · 0 val. | documenté + précisé par les données |
| `discount.type` | 1 %, 2 montant/jour, 3 montant fixe, 4 aucune, 5 plan, 6 montant fixe caché, 7 montant fixe affiché en %, 8 package. Ici toujours 7. | 7 (27) | entier · présent 0.5 % · rempli 0.5 % · 1 val. | documenté |
| `discount.value` | Valeur de la remise (ici un % calculé : (prix nuits − amount) / prix nuits × 100). | 15.083798882681565, 9.615384615384615, 9.836065573770492 | décimal · présent 0.5 % · rempli 0.5 % · 27 val. | documenté + précisé par les données |
| `discount.code` | Code utilisé (« YB: Custom Discount » = remise saisie à la main dans YouBook). | "YB: Custom Discount" (27) | texte · présent 0.5 % · rempli 0.5 % · 1 val. | documenté + précisé par les données |
| `discount.name` | Nom de la remise. | "YB: Custom Discount" (27) | texte · présent 0.5 % · rempli 0.5 % · 1 val. | documenté |
| `discount.id` | Id de la remise (vide ici). | "" (27) | texte · présent 0.5 % · rempli 0.0 % · 1 val. | documenté |
| `discount.pricing_plan` | Plan lié (-1 = aucun). | -1 (27) | entier · présent 0.5 % · rempli 0.5 % · 1 val. | documenté |
| `mandatory_costs` | (Documenté, jamais présent ici) frais obligatoires, réservations directes. | — | jamais présent | documenté |
| `ancillary` | (Documenté au niveau réservation avec ancillary=1, jamais présent ici au premier niveau ; les infos ancillary sont dans booked_rooms.) | — | jamais présent | documenté |

## 5b. Détails Booking.com (booked_rooms[].ancillary et roomdays[].ancillary)

| Champ | Sens | Exemple / valeurs | Données | Fiabilité |
|---|---|---|---|---|
| `booked_rooms[].ancillary.channel_room_id` | Id de la chambre côté Booking. | 5531912 (1925), 5531910 (539), 5531904 (231), 5531916 (189), 5531915 (79), 5531919 (58), 5531917 (58), 5531920 (31), 5531918 (26), 5531921 (19) | entier · présent 54.9 % · rempli 54.9 % · 10 val. | déduit, non documenté |
| `booked_rooms[].ancillary.channel_room_name` | Nom de la chambre côté Booking (ex. « Chambre Double ou Lits Jumeaux Économique - Single Use »). | "Chambre Double ou Lits Jumeaux Économique" (1621), "Chambre Double ou Lits Jumeaux avec Balcon" (398), "Chambre Double ou Lits Jumeaux Économique - Single Use" (304), "Chambre Triple Standard" (231), "Chambre Lits Jumeaux" (189), "Chambre Double ou Lits Jumeaux avec Balcon - Single Use" (141), "Chambre Lits Jumeaux avec Balcon" (79), "Chambre Familiale avec Balcon" (58), "Chambre Triple avec Balcon" (58), "Chambre Triple Classique" (31), "Chambre Familiale Standard" (26), "Chambre Triple Confort" (19) | texte · présent 54.9 % · rempli 54.9 % · 12 val. | déduit, non documenté |
| `booked_rooms[].ancillary.channel_roomreservation_id` | N° de la chambre-réservation chez Booking (une par chambre). | "6144851065" | texte · présent 54.9 % · rempli 54.9 % · 3013 val. | déduit, non documenté |
| `booked_rooms[].ancillary.guest_name` | Nom de l'occupant de la chambre. | texte (nom de l'occupant) | texte · présent 54.9 % · rempli 54.9 % · 2626 val. | déduit, non documenté |
| `booked_rooms[].ancillary.guests` | Nombre de personnes dans la chambre. | 2 (1591), 1 (1187), 3 (302), 4 (75) | entier · présent 54.9 % · rempli 54.9 % · 4 val. | déduit, non documenté |
| `booked_rooms[].ancillary.guests_adults` | Adultes dans la chambre. | 2 (1661), 1 (1303), 3 (171), 4 (20) | entier · présent 54.9 % · rempli 54.9 % · 4 val. | déduit, non documenté |
| `booked_rooms[].ancillary.guests_children` | Enfants dans la chambre. | 0 (2866), 1 (221), 2 (68) | entier · présent 54.9 % · rempli 4.9 % · 3 val. | déduit, non documenté |
| `booked_rooms[].ancillary.occupancy_children` | Liste des âges des enfants. | (structure) | liste · présent 54.9 % · rempli 4.9 % · 0 val. | déduit, non documenté |
| `booked_rooms[].ancillary.occupancy_children[].age` | Âge de l'enfant. | 11, 15, 12 | entier · présent 4.9 % · rempli 4.6 % · 18 val. | déduit, non documenté |
| `booked_rooms[].ancillary.occupancy_children[].count` | Nombre d'enfants de cet âge. | 1 (345), 2 (6) | entier · présent 4.9 % · rempli 4.9 % · 2 val. | déduit, non documenté |
| `booked_rooms[].ancillary.addons` | Liste de suppléments au niveau chambre (toujours vide). | (structure) | liste · présent 54.9 % · rempli 0.0 % · 0 val. | déduit, non documenté |
| `booked_rooms[].ancillary.extracomponents` | Taxes détaillées par Booking : une ligne « TVA » et une ligne « taxe de séjour ». | (structure) | liste · présent 54.9 % · rempli 54.9 % · 0 val. | déduit, non documenté |
| `booked_rooms[].ancillary.extracomponents[].description` | « TVA » ou « taxe de séjour ». | "TVA" (3155), "taxe de séjour" (3155) | texte · présent 54.9 % · rempli 54.9 % · 2 val. | déduit, non documenté |
| `booked_rooms[].ancillary.extracomponents[].amount` | Montant total de la taxe pour la chambre (ex. TVA 11.15 sur 122.64 = 10 %). | 6.0, 4.0, 3.0 | décimal · présent 54.9 % · rempli 54.9 % · 1465 val. | déduit, non documenté |
| `booked_rooms[].ancillary.extracomponents[].amount_included` | true = déjà inclus dans le prix (TVA) ; false = à ajouter (taxe de séjour). | true (3171), false (3125) | booléen · présent 54.8 % · rempli 54.8 % · 2 val. | déduit, non documenté |
| `booked_rooms[].ancillary.extracomponents[].per_night` | true = calculé par nuit. | false (3171), true (3125) | booléen · présent 54.8 % · rempli 54.5 % · 2 val. | déduit, non documenté |
| `booked_rooms[].ancillary.extracomponents[].per_person` | true = calculé par personne. | false (3171), true (3125) | booléen · présent 54.8 % · rempli 54.5 % · 2 val. | déduit, non documenté |
| `booked_rooms[].ancillary.extracomponents[].currency` | Devise. | "EUR" (6310) | texte · présent 54.9 % · rempli 54.9 % · 1 val. | déduit, non documenté |
| `booked_rooms[].roomdays[].ancillary.channel_rate_id` | Id du tarif côté OTA (102016 = Standard Rate, 44238293 = Double PDJ inclus…). | "102016" (4119), "44238293" (1693), "44238345" (67), "44238409" (11) | texte · présent 54.9 % · rempli 54.9 % · 4 val. | déduit, non documenté |
| `booked_rooms[].roomdays[].ancillary.channel_rate_name` | Nom du tarif côté OTA (Booking et Expedia). | "Standard Rate" (4119), "Double Petit-déjeuner inclus" (1693), "Standard7j (Standalone)" (750), "StandardBB7j (Standalone)" (225), "Standard (Standalone)" (220), "Breakfast include Standard (Standalone)" (146), "Triple Petit-déjeuner inclus" (67), "Breakfast included (Standalone)" (59), "Breakfast included. (Standalone)" (38), "Standard7jBB (Standalone)" (18), "NR (7 nuits)" (11) | texte · présent 65.2 % · rempli 65.2 % · 11 val. | déduit, non documenté |
| `booked_rooms[].roomdays[].ancillary.booked_derived_rate` | Tarif dérivé/promo Booking appliqué (« Standard Rate Flex 7j », « Last Minute Deal », « Mobile(App) Rate », « Black Friday Deal »…). | "Standard Rate Flex 7j", "Double BB Flex 7j", "Last Minute Deal" | texte · présent 49.4 % · rempli 49.4 % · 14 val. | déduit, non documenté |

## 5c. Détails Expedia

| Champ | Sens | Exemple / valeurs | Données | Fiabilité |
|---|---|---|---|---|
| `booked_rooms[].ancillary.expedia_payment_model` | Modèle de paiement Expedia (toujours « n/d »). | "n/d" (522) | texte · présent 10.3 % · rempli 10.3 % · 1 val. | déduit, non documenté |
| `booked_rooms[].ancillary.expedia_payment_method` | Moyen de paiement Expedia (toujours « n/d »). | "n/d" (522) | texte · présent 10.3 % · rempli 10.3 % · 1 val. | déduit, non documenté |
| `booked_rooms[].ancillary.expedia_payment_amount` | Montant payé via Expedia (toujours « n/d »). | "n/d" (522) | texte · présent 10.3 % · rempli 10.3 % · 1 val. | déduit, non documenté |
| `booked_rooms[].ancillary.expedia_compensation_inclusive` | Commission incluse ou non (toujours false). | false (522) | booléen · présent 10.3 % · rempli 0.0 % · 1 val. | déduit, non documenté |
| `booked_rooms[].ancillary.tax_inclusive` | true = prix TTC. | true (520), false (2) | booléen · présent 10.3 % · rempli 10.2 % · 2 val. | déduit, non documenté |
| `booked_rooms[].ancillary.taxes` | Taxes ajoutées par Expedia (2 cas à 9.46 €, et alors amount = nuits + taxes). | 0.0 (520), 9.46 (2) | décimal · présent 10.3 % · rempli 0.0 % · 2 val. | déduit, non documenté |
| `booked_rooms[].ancillary.fees` | Frais Expedia (toujours 0). | 0.0 (522) | décimal · présent 10.3 % · rempli 0.0 % · 1 val. | déduit, non documenté |
| `booked_rooms[].roomdays[].ancillary.promoName` | Promo Expedia appliquée à la nuit (« Offre Mobile 10%-Members », « September Sale 2026-Members »…). | "Contracted Improved Member Only ", "Offre Mobile 10%-Members", "September Sale 2026-Members" | texte · présent 10.3 % · rempli 10.3 % · 18 val. | déduit, non documenté |
| `booked_rooms[].roomdays[].ancillary.additional_guests_amount` | Supplément personnes additionnelles (toujours liste vide). | (structure) | liste · présent 10.3 % · rempli 0.0 % · 0 val. | déduit, non documenté |

## 6. Paiement / carte

| Champ | Sens | Exemple / valeurs | Données | Fiabilité |
|---|---|---|---|---|
| `payment_gateway_fee` | Montant payé en ligne par le client (acompte) sur le moteur du site. Texte vide si rien ; ici égal à amount à chaque fois (paiement intégral). | 43.65, 72.0, 85.0 | texte/décimal · présent 100.0 % · rempli 5.6 % · 269 val. | documenté + précisé par les données |
| `cc_info` | 1 = une carte bancaire est enregistrée dans WuBook pour cette résa, 0 sinon. Les données de carte ne sont PAS dans la réponse (consultables seulement dans l'extranet). Pour info, la doc de new_reservation décrit les champs carte cc_number, cc_owner, cc_exp_month, cc_exp_year, cc_cvv, cc_type — jamais renvoyés par fetch. | 0 (5030), 1 (62) | entier · présent 100.0 % · rempli 1.2 % · 2 val. | déduit, non documenté |

## 7. Annulation (présents uniquement si annulée)

| Champ | Sens | Exemple / valeurs | Données | Fiabilité |
|---|---|---|---|---|
| `deleted_at_time` | Date et heure d'annulation (JJ/MM/AAAA HH:MM:SS). | "19/10/2026 00:01:48" | texte · présent 16.4 % · rempli 16.4 % · 835 val. | documenté |
| `deleted_at` | Date d'annulation seule. Obsolète. | "10/06/2026", "18/05/2026", "01/06/2026" | texte · présent 16.4 % · rempli 16.4 % · 392 val. | documenté |
| `deleted_advance` | Nombre de jours entre l'annulation et l'arrivée (0 = le jour même ; vérifié = arrivée − date d'annulation dans 99 % des cas). | 1, 10, 8 | entier · présent 16.4 % · rempli 15.5 % · 151 val. | documenté + précisé par les données |
| `deleted_from` | Origine de l'annulation : 1 client (site), 2 back-office (vous), 3 canal OTA, 4 staff WuBook, 5 Alien, 6 Wired (API), 7 passerelle de paiement, 8 annulée suite à une modification. | 3 (611), 8 (117), 1 (62), 7 (22), 2 (21), 6 (2) | entier · présent 16.4 % · rempli 16.4 % · 6 val. | documenté |

## Pièges

1. **`dayprices` ne sert pas à compter.** Il est indexé par TYPE de chambre : deux chambres du même type dans une résa sont fusionnées. Il n'est pas arrondi, et la doc le déclare obsolète pour les OTA. Pour compter les chambres-nuits et le CA hébergement, utiliser `booked_rooms[].roomdays[]` (`day`, `price`). Une ligne = une chambre × une nuit.
2. **`amount` ≠ somme des `roomdays[].price`. C'est normal :**
   - **Site (wowowowo…) et Google Free Booking Link :** `amount` = nuits + extras de `addons_list` (petit-déjeuner, parking…). L'écart s'explique entièrement par les extras (1 seule résa sur 633 a un écart résiduel de 7,99 €).
   - **Manuel (YouBook) :** `amount` = prix final saisi. Il est en général égal à nuits + extras. Dans 26 cas il est plus bas que les nuits à cause d'une remise (`discount.code` = « YB: Custom Discount »), et dans 10 cas il est forcé (`forced_price` = 1). Dans ces cas, les `roomdays[].price` sont les prix AVANT remise, et `amount` est le vrai montant.
   - **Booking :** `amount` = somme des nuits exactement, TVA comprise. La taxe de séjour est dans `addons_list` (« taxe de séjour », `price` unitaire × `req`) et dans `extracomponents` avec `amount_included`=false. Elle n'est PAS dans `amount`.
   - **Expedia :** `amount` = nuits, plus `booked_rooms[].ancillary.taxes` quand il y en a (2 cas).
   - **Canal 43 :** `amount` = nuits + `PASS_THROUGH_CLEANING_FEE` (`channel_data.addons_embedded` = true).
   - **Alien :** prix forcé (`forced_price`=1). Tout l'écart vient de 5 réservations de test du 12/12/2025 (note « Test », 300 € saisis pour 45 € de nuits) ; les vraies résas Alien sont égales aux nuits.
   - **`city_tax` n'est jamais incluse dans `amount`.** Elle n'est calculée que pour les réservations hors OTA.
   - **CA hébergement :** somme des `roomdays[].price`, sauf pour les résas manuelles remisées ou forcées, où il faut partir de `amount` moins les extras. **CA total encaissé :** `amount`, et pour une vue client ajouter `city_tax` ou la taxe de séjour Booking.
3. **Format des dates :** texte européen « JJ/MM/AAAA », sans fuseau, en heure de Paris. `date_received_time` et `deleted_at_time` ajoutent « HH:MM:SS ». Les champs `vcc_valid_from` et `vcc_valid_til` sont en revanche des horodatages Unix. `reservation_code` est lui aussi un horodatage Unix, celui de la création. Le jour de départ n'est pas une nuit.
4. **Statuts :** sont confirmées `status` 1 et 4 (4 = acceptée, site seulement). 2 = en attente, 3 = refusée par la passerelle de paiement ; elles ne sont pas des ventes. 5 = annulée. Il n'existe pas de statut « modifiée ».
5. **Modifications OTA :** l'ancienne résa passe en `status`=5 avec `was_modified`=1 et `deleted_from`=8. Une NOUVELLE résa (nouveau `reservation_code`) porte dans `modified_reservations` le code qu'elle remplace. Il ne faut compter que la nouvelle. 117 résas sont dans ce cas (Booking 111, Expedia 6).
6. **Annulées :** seules elles ont `deleted_at`, `deleted_at_time`, `deleted_advance` et `deleted_from`, soit 4 clés de plus : 54 clés au lieu de 50. `status_reason` contient alors souvent la note OTA, ou « Unknown reason ».
7. **`roomnight` n'est pas le nombre de chambres-nuits** (c'est environ nuits × adultes). `booked_rate` est obsolète ; utiliser `roomdays[].rate_id`.
8. **Types variables :** `special_offer` et `boards` valent "" (texte) quand ils sont vides, et un objet sinon. `id_woodoo` est "" ou un entier. `payment_gateway_fee` est "" ou un décimal. Il faut tester le type avant de lire.
9. **Saisie manuelle (YouBook) :** téléphone, comptoir et mail y sont mélangés, il est impossible de les distinguer.
10. **Le canal 43 = Airbnb est une déduction.** Elle repose sur les codes « HM… » et les frais « PASS_THROUGH ». Il n'y a pas eu d'appel `get_channels_info` pour la confirmer.
