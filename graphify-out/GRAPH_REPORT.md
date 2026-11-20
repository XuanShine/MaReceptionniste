# Graph Report - MaReceptionniste  (2026-11-19)

## Corpus Check
- 91 files · ~61,404 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 9 file(s) not represented in the graph (top: .mdc 3, .odt 3, (none) 2)

## Summary
- 1473 nodes · 5145 edges · 52 communities (46 shown, 6 thin omitted)
- Extraction: 83% EXTRACTED · 17% INFERRED · 0% AMBIGUOUS · INFERRED: 866 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Disponibilités par type
- Catalogue produits
- Auth réceptionniste
- Fiche séjour saisie
- Envoi email facture
- Consommation ponctuelle
- Calcul facture
- Taxe de séjour
- Émission de facture
- Catalogue chambres saisie
- Page paramètres
- Modèle ODT facture
- Import Wubook
- Écriture fiche séjour
- Droits et rapports
- Rendu PDF facture
- App gouvernante et base
- Clients et tableau de bord
- Consultations planning
- Ménage des chambres
- Migrations SQLite
- Tests migrations schéma
- Données de démonstration
- États des chambres
- Navigation gouvernante
- Tests UI paramètres
- Contexte ODT facture
- Auth gouvernante
- Identité de facturation
- Tests saisie catalogue
- Tests UI fiche
- Grille planning
- Exemple facture démo
- Recherche clients
- Saisie ponctuelle fiche
- Totaux séjour
- Contraintes NiceGUI
- Contrat données facture
- Tests modèles SQL
- Config et secrets
- Évolution du schéma
- Tests UI facture
- Modèles facturation
- Template LibreOffice
- Async et pages UI
- Statuts de réservation
- Fixture base tests
- Redirection anciennes chambres
- Paquet ma-receptionniste
- TODO hashtag

## God Nodes (most connected - your core abstractions)
1. `get_session()` - 92 edges
2. `fiche()` - 86 edges
3. `fiche_sejour()` - 56 edges
4. `Chambre` - 53 edges
5. `Reservation` - 51 edges
6. `TypeChambre` - 50 edges
7. `CatalogueInvalide` - 41 edges
8. `StatutReservation` - 39 edges
9. `preparer_apercu()` - 37 edges
10. `creer_client()` - 35 edges

## Surprising Connections (you probably didn't know these)
- `Archives des formules virtuelles` --semantically_similar_to--> `Archive de facture immuable`  [INFERRED] [semantically similar]
  README.md → templates/factures/README.md
- `test_les_statuts_affichables()` --uses--> `StatutReservation`  [INFERRED]
  tests/test_statut.py → src/ma_receptionniste/models.py
- `test_creer_client()` --uses--> `Client`  [INFERRED]
  tests/test_models.py → src/ma_receptionniste/models.py
- `Solde de la facture de démonstration` --conceptually_related_to--> `Taxe de séjour`  [INFERRED]
  templates/factures/exemple_facture.pdf → README.md
- `ColonneNonAjoutable` --semantically_similar_to--> `StrictUndefined`  [INFERRED] [semantically similar]
  README.md → templates/factures/README.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Production du PDF de facture** — templates_factures_readme_facture_hotel_odt, templates_factures_readme_rendre_modele, templates_factures_readme_contrat_donnees, templates_factures_readme_python_odt_template, readme_libreoffice, templates_factures_readme_archive_immuable [INFERRED 0.95]
- **Modèles mentaux NiceGUI** — llms_no_virtual_dom, llms_shared_module_state, llms_ui_page, llms_slot_stack, llms_bindings, llms_python_first, llms_shared_event_loop, llms_app_storage, llms_outbox, llms_response_timeout [EXTRACTED 1.00]
- **Lecture et écriture d'un séjour** — readme_enregistrer_sejour, readme_saisie, readme_consultations, readme_facturation [INFERRED 0.75]

## Communities (52 total, 6 thin omitted)

### Community 0 - "Disponibilités par type"
Cohesion: 0.06
Nodes (50): disponibilites_par_type(), matrice_disponibilites(), Historique, Reservation, Sejour, _charger_disponibilites(), disponibilites(), afficher() (+42 more)

### Community 1 - "Catalogue produits"
Cohesion: 0.07
Nodes (52): lister_produits(), Produit, badge(), _champ_prix(), _champ_tva(), _euros(), _libelle_taux(), _prix_saisi() (+44 more)

### Community 2 - "Auth réceptionniste"
Cohesion: 0.05
Nodes (37): authenticate(), AuthMiddleware, current_user(), EmailDejaUtilise, hash_password(), login_user(), normalize_email(), safe_redirect() (+29 more)

### Community 3 - "Fiche séjour saisie"
Cohesion: 0.07
Nodes (52): _barre_saisie(), _boutons_brouillon(), _catalogue_chambres(), _champs(), _confirmation(), _entete(), fiche(), abandonner() (+44 more)

### Community 4 - "Envoi email facture"
Cohesion: 0.06
Nodes (28): ApercuPerime, email_du_sejour(), email_valide(), envoi_configure(), _envoyer(), envoyer_facture(), _journaliser(), _transmettre() (+20 more)

### Community 5 - "Consommation ponctuelle"
Cohesion: 0.09
Nodes (36): basculer(), _canonique(), _canonique_consommation(), _champ(), cle_chambre(), _comme_date(), _comme_nombre(), ecrire() (+28 more)

### Community 6 - "Calcul facture"
Cohesion: 0.11
Nodes (45): ApercuFacture, appliquer_taxe_et_reglements(), calculer_totaux(), _chargement_facture(), _charger(), _code(), _composer(), _contenu() (+37 more)

### Community 7 - "Taxe de séjour"
Cohesion: 0.09
Nodes (43): options_chambres(), centimes(), taxe_sejour(), _ajuster_depart(), BrouillonLigne, _cellule_saisie(), _champ_date(), _champ_euros() (+35 more)

### Community 8 - "Émission de facture"
Cohesion: 0.14
Nodes (41): contenu_apercu(), emettre_facture(), Facture, lire_facture(), lister_factures(), obtenir_facture_courante(), preparer_apercu(), RemplacementInterdit (+33 more)

### Community 9 - "Catalogue chambres saisie"
Cohesion: 0.13
Nodes (43): OccupationChambre, _bandeau(), _fait(), attribuer_chambres_virtuelles(), attribuer_occupation_chambre(), attribuer_type_chambre(), basculer_etat(), CatalogueInvalide (+35 more)

### Community 10 - "Page paramètres"
Cohesion: 0.08
Nodes (41): etat_vide(), _avec_choix(), _champ_prix(), _champ_raccourci(), _conserver(), _lien(), _options_occupations(), _options_types() (+33 more)

### Community 11 - "Modèle ODT facture"
Cohesion: 0.10
Nodes (16): cellule(), champ(), construire_modele(), contenu_document(), directive_row(), ligne(), main(), p() (+8 more)

### Community 12 - "Import Wubook"
Cohesion: 0.11
Nodes (25): ChambreChambreVirtuelle, ChambreVirtuelle, ImportWubookImpossible, mettre_a_jour_types_wubook(), _refuser_affectations_ambigues(), _valider_catalogue(), echouer(), affectations_virtuelles() (+17 more)

### Community 13 - "Écriture fiche séjour"
Cohesion: 0.12
Nodes (38): _avec_tout(), _bornes(), fiche_sejour(), lister_reservations(), StatutReservation, annuler_reservation(), _comparable(), _coordonnees_modifiees() (+30 more)

### Community 14 - "Droits et rapports"
Cohesion: 0.15
Nodes (27): detail(), peut(), Refus, libelle_etat(), libelle_menage(), _carte_rapport(), chambre(), rapports() (+19 more)

### Community 15 - "Rendu PDF facture"
Cohesion: 0.10
Nodes (17): chemin_modele(), convertir_pdf(), rendre_odt(), dossier_factures(), generer_pdf(), generer_pdf_apercu(), _noter_pdf(), _produire() (+9 more)

### Community 16 - "App gouvernante et base"
Cohesion: 0.11
Nodes (18): AuthMiddleware, _activer_cles_etrangeres(), create_db_and_tables(), main(), demarrer(), GouvernanteModel, Historique, Signalement (+10 more)

### Community 17 - "Clients et tableau de bord"
Cohesion: 0.10
Nodes (25): logout_user(), charger_resume(), lister_clients(), ResumeJour, clients(), _afficher(), ajouter(), dashboard() (+17 more)

### Community 18 - "Consultations planning"
Cohesion: 0.11
Nodes (21): Affichage, _chambre_dict(), charger_planning(), _client_dict(), _etat(), _libelle_type(), _lire_chambres(), lire_client() (+13 more)

### Community 19 - "Ménage des chambres"
Cohesion: 0.17
Nodes (28): utilisateur(), changer_etat(), get_session(), exiger(), ajouter(), ajouter_chambres_en_service(), assurer_liste(), changer_statut() (+20 more)

### Community 20 - "Migrations SQLite"
Cohesion: 0.12
Nodes (21): _a_colonne(), _activer_cles_etrangeres(), _ajouter_champs_type_chambre(), _appliquer(), _archiver_anciennes_cellules_virtuelles(), CatalogueIllisible, ColonneNonAjoutable, _creer_tables_catalogue() (+13 more)

### Community 21 - "Tests migrations schéma"
Cohesion: 0.21
Nodes (26): ajouter_colonnes_manquantes(), create_db_and_tables(), Chambre, ancienne_base(), _colonnes(), _index(), _sql(), test_ancienne_base_recoit_les_nouvelles_colonnes() (+18 more)

### Community 22 - "Données de démonstration"
Cohesion: 0.15
Nodes (22): _adresse_si_absente(), _chambre(), _existe(), _historique(), _id_type(), main(), _reception(), _reservation() (+14 more)

### Community 23 - "États des chambres"
Cohesion: 0.17
Nodes (23): ChambreIntrouvable, creer_chambre(), _etat(), EtatInvalide, NomDejaPris, NomVide, tableau(), EtatChambre (+15 more)

### Community 24 - "Navigation gouvernante"
Cohesion: 0.15
Nodes (15): logout_user(), lister(), libelle_role(), accueil(), historique(), _courant(), icone(), _initiales() (+7 more)

### Community 25 - "Tests UI paramètres"
Cohesion: 0.19
Nodes (20): ecran_parametres(), TypeChambre, catalogue(), catalogue_disponibilites(), catalogue_parametres(), _ouvrir_parametres(), test_creation_chambre_avec_etage(), test_creation_chambre_avec_plusieurs_virtuelles() (+12 more)

### Community 26 - "Contexte ODT facture"
Cohesion: 0.17
Nodes (20): format_euros(), libelle_taux(), nuits(), _complements(), _contexte(), contexte_apercu(), contexte_facture(), ContexteFactureODT (+12 more)

### Community 27 - "Auth gouvernante"
Cohesion: 0.17
Nodes (18): assurer_comptes(), authenticate(), charger_utilisateur(), hash_password(), normalize_email(), safe_redirect(), verify_password(), Role (+10 more)

### Community 28 - "Identité de facturation"
Cohesion: 0.18
Nodes (21): _assurer_identite(), _copier_identite(), enregistrer_identite(), _identite_de_session(), identite_vide(), IdentiteFacturation, _lignes_hotel(), lire_identite() (+13 more)

### Community 29 - "Tests saisie catalogue"
Cohesion: 0.25
Nodes (17): creer_chambre(), creer_occupation_chambre(), creer_type_chambre(), test_affectation_virtuelle_invalide_ne_modifie_rien(), test_affectations_virtuelles_multiples_partagees_et_independantes_du_type(), test_chambre_virtuelle_du_catalogue(), test_creer_chambre_prend_les_identifiants_en_mot_cle(), test_echec_de_creation_chambre_ne_cree_pas_de_liens() (+9 more)

### Community 30 - "Tests UI fiche"
Cohesion: 0.28
Nodes (17): register_user(), _champ(), _ligne_consommation(), _ouvrir_session(), _reservation_de_la_capture(), test_abandon_garde_le_client_initial(), test_ajouter_une_ligne_s_inscrit_dans_le_tableau(), test_la_fiche_montre_la_ligne_les_actions_et_le_total() (+9 more)

### Community 31 - "Grille planning"
Cohesion: 0.22
Nodes (14): nom_planning(), segments(), _bloc(), _entete_jour(), _fond(), _grille(), _ligne(), _lundi() (+6 more)

### Community 32 - "Exemple facture démo"
Cohesion: 0.19
Nodes (14): Aperçu de facture, Bandeau document non comptable, Blocs client et séjour, Palette violet olive lavande, Tableaux chambres et consommations, Conditions de règlement de l'exemple, Facture de démonstration, Hôtel Panorama (+6 more)

### Community 33 - "Recherche clients"
Cohesion: 0.21
Nodes (14): appliquer(), _detail_client(), libelle_client(), normaliser_nom(), _proximite(), rechercher_clients(), _dialogue_clients(), afficher() (+6 more)

### Community 34 - "Saisie ponctuelle fiche"
Cohesion: 0.19
Nodes (15): _alerte_ponctuelle(), _entete_ponctuel(), _entier_positif(), _colonnes_ponctuelles(), executer_ponctuelle(), _notes_paire(), _paire_ponctuelle(), changer_case() (+7 more)

### Community 35 - "Totaux séjour"
Cohesion: 0.18
Nodes (12): montant_consommation(), montant_ligne(), montant_sejour(), Totaux, totaux(), sejour(), test_centimes_depuis_une_saisie_en_euros(), test_format_euros() (+4 more)

### Community 36 - "Contraintes NiceGUI"
Cohesion: 0.18
Nodes (8): NiceGUI, Fixture Screen, Fixture User, Layout, Démarrage, Pages, Test d'interface fiche, Thème

### Community 37 - "Contrat données facture"
Cohesion: 0.22
Nodes (11): Facturation, format_euros, Saisie journalisée, Taxe de séjour, Récapitulatif lavande, Solde de la facture de démonstration, Contrat de données de facture, Lignes de prestations (+3 more)

### Community 38 - "Tests modèles SQL"
Cohesion: 0.19
Nodes (5): base_relations(), test_creer_client(), test_liaison_unique_et_cles_etrangeres_actives(), test_relations_chambres_virtuelles_dans_les_deux_sens(), test_suppression_en_cascade_des_liaisons()

### Community 39 - "Config et secrets"
Cohesion: 0.18
Nodes (10): app.storage, storage_secret, Authentification, DATABASE_URL, Données de démonstration, HOST et PORT, Ma Réceptionniste, PUBLIC_ROUTES (+2 more)

### Community 40 - "Évolution du schéma"
Cohesion: 0.22
Nodes (8): ajouter_colonnes_manquantes, Alembic, anchorate, ColonneNonAjoutable, create_db_and_tables, Import des types de chambres Wubook, SQLModel, subroom

### Community 41 - "Tests UI facture"
Cohesion: 0.51
Nodes (7): _attendre_apercu(), _champ(), _ouvrir(), _sejour(), test_apercu_bloque_sans_mentions(), test_apercu_puis_enregistrement(), test_parametres_enregistrent_l_identite_incomplete()

### Community 42 - "Modèles facturation"
Cohesion: 0.38
Nodes (7): _ajouter_details(), CompteurFacture, Consommation, LigneFacture, Reglement, ReglementFacture, VentilationTVA

### Community 43 - "Template LibreOffice"
Cohesion: 0.25
Nodes (6): LibreOffice, facture_hotel.odt, ODTTemplate, python-odt-template, rendre_modele, Édition du template facture_odt

### Community 44 - "Async et pages UI"
Cohesion: 0.33
Nodes (3): background_tasks.create, run.cpu_bound, run.io_bound

### Community 45 - "Statuts de réservation"
Cohesion: 0.50
Nodes (5): Consultations, enregistrer_sejour, Reservation, Statut de groupe par chambre, StatutReservation

## Ambiguous Edges - Review These
- `Démonstration non émise` → `Bandeau document non comptable`  [AMBIGUOUS]
  templates/factures/README.md · relation: conceptually_related_to

## Knowledge Gaps
- **11 isolated node(s):** `ma-receptionniste`, `uv`, `Layout`, `Alembic`, `Hashtag` (+6 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 241 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `fiche()` connect `Fiche séjour saisie` to `Disponibilités par type`, `Catalogue produits`, `Recherche clients`, `Saisie ponctuelle fiche`, `Envoi email facture`, `Consommation ponctuelle`, `Taxe de séjour`, `Émission de facture`, `Page paramètres`, `Écriture fiche séjour`, `Clients et tableau de bord`, `Contexte ODT facture`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._
- **Are the 20 inferred relationships involving `get_session()` (e.g. with `_adresse_si_absente()` and `_chambre()`) actually correct?**
  _`get_session()` has 20 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ma-receptionniste`, `uv`, `Layout` to the rest of the system?**
  _11 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Disponibilités par type` be split into smaller, more focused modules?**
  _Cohesion score 0.063568010936432 - nodes in this community are weakly interconnected._
- **Why does `get_session()` connect `Données de démonstration` to `Disponibilités par type`, `Catalogue produits`, `Auth réceptionniste`, `Envoi email facture`, `Consommation ponctuelle`, `Calcul facture`, `Émission de facture`, `Catalogue chambres saisie`, `Import Wubook`, `Écriture fiche séjour`, `Rendu PDF facture`, `Clients et tableau de bord`, `Consultations planning`, `Migrations SQLite`, `Tests UI paramètres`, `Identité de facturation`, `Tests saisie catalogue`, `Tests UI fiche`, `Tests UI facture`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Are the 20 inferred relationships involving `fiche()` (e.g. with `NoteIllisible` and `fiche_sejour()`) actually correct?**
  _`fiche()` has 20 INFERRED edges - model-reasoned connections that need verification._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `Démonstration non émise` and `Bandeau document non comptable`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._