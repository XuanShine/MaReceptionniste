"""Écritures de la fiche séjour, appelées comme le font les pages, et ce que la fiche relit ensuite."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from ma_receptionniste.consultations import (
    ecran_parametres,
    fiche_sejour,
    libelle_client,
    lister_clients,
    lister_reservations,
    normaliser_nom,
    rechercher_clients,
)
from ma_receptionniste.db import get_session
from ma_receptionniste.facturation import IdentiteFacturation, enregistrer_identite
from ma_receptionniste.models import FormeJuridique, ModeReglement, RegimeTVA, Reservation, StatutReservation, User
from ma_receptionniste.saisie import (
    NOM_CLIENT_PASSAGE,
    CatalogueInvalide,
    FacturationImpossible,
    FicheInvalide,
    ajouter_consommation,
    ajouter_reglement,
    ajouter_sejour,
    annuler_reservation,
    attribuer_chambres_virtuelles,
    attribuer_type_chambre,
    creer_chambre,
    creer_chambre_virtuelle,
    creer_client,
    creer_occupation_chambre,
    creer_reservation,
    creer_type_chambre,
    enregistrer_chambre_virtuelle,
    enregistrer_fiche,
    enregistrer_type_chambre,
    facturer,
    modifier_etage_chambre,
    modifier_occupation_chambre,
    modifier_sejour,
    renommer_type_chambre,
    reprendre_reservation,
    supprimer_chambre_virtuelle,
    supprimer_occupation_chambre,
    supprimer_sejour,
    supprimer_type_chambre,
)
from ma_receptionniste.sejours import ChambreOccupee

ARRIVEE = date(2026, 10, 18)
DEPART = date(2026, 10, 20)


@pytest.fixture
def reception(base) -> int:
    with Session(base) as session:
        user = User(email="reception@hotel-panorama.fr", nom="Réception", password_hash="x")
        session.add(user)
        session.commit()
        return user.id


def nouvelle_reservation() -> int:
    return creer_reservation(creer_client("LE CLOEREC"))


def descriptions(reservation_id: int) -> list[str]:
    return [note["description"] for note in fiche_sejour(reservation_id)["historique"]]


def test_affectations_virtuelles_multiples_partagees_et_independantes_du_type(base) -> None:
    double = creer_type_chambre("Double")
    suite = creer_type_chambre("Suite")
    v1 = creer_chambre_virtuelle(double, "V1", 80, 50)
    v2 = creer_chambre_virtuelle(suite, "V2", 90, 60)
    chambre1 = creer_chambre("101", 1, type_chambre_id=double, chambres_virtuelles_ids=[v1, v2, v1])
    chambre2 = creer_chambre("102", 2, chambres_virtuelles_ids=[v1])
    chambre3 = creer_chambre("103", 3)

    chambres = {ligne["id"]: ligne for ligne in ecran_parametres()["chambres"]}
    assert set(chambres[chambre1]["chambres_virtuelles_ids"]) == {v1, v2}
    assert chambres[chambre2]["chambres_virtuelles_ids"] == [v1]
    assert chambres[chambre3]["chambres_virtuelles_ids"] == []
    assert not attribuer_chambres_virtuelles(chambre1, [v2, v1])
    assert attribuer_type_chambre(chambre1, suite)
    assert attribuer_chambres_virtuelles(chambre2, [])
    chambres = {ligne["id"]: ligne for ligne in ecran_parametres()["chambres"]}
    assert set(chambres[chambre1]["chambres_virtuelles_ids"]) == {v1, v2}
    assert chambres[chambre2]["chambres_virtuelles_ids"] == []


def test_affectation_virtuelle_invalide_ne_modifie_rien(base) -> None:
    type_id = creer_type_chambre("Double")
    virtuelle = creer_chambre_virtuelle(type_id, "V1", 80, 50)
    chambre = creer_chambre("101", 1, chambres_virtuelles_ids=[virtuelle])

    with pytest.raises(CatalogueInvalide, match="virtuelle est introuvable"):
        attribuer_chambres_virtuelles(chambre, [virtuelle, 99999])
    with pytest.raises(CatalogueInvalide, match="virtuelle est introuvable"):
        creer_chambre("102", 2, chambres_virtuelles_ids=[99999])
    with pytest.raises(CatalogueInvalide, match="chambre est introuvable"):
        attribuer_chambres_virtuelles(99999, [])
    chambres = ecran_parametres()["chambres"]
    assert len(chambres) == 1
    assert chambres[0]["chambres_virtuelles_ids"] == [virtuelle]


def test_echec_de_creation_chambre_ne_cree_pas_de_liens(base) -> None:
    type_id = creer_type_chambre("Double")
    v1 = creer_chambre_virtuelle(type_id, "V1", 80, 50)
    v2 = creer_chambre_virtuelle(type_id, "V2", 90, 60)
    creer_chambre("101", 1, chambres_virtuelles_ids=[v1])
    with pytest.raises(IntegrityError):
        creer_chambre("101", 2, chambres_virtuelles_ids=[v2])
    chambres = ecran_parametres()["chambres"]
    assert len(chambres) == 1
    assert chambres[0]["chambres_virtuelles_ids"] == [v1]


def test_enregistrer_fiche_ecrit_et_journalise_les_champs_changes(reception: int) -> None:
    reservation_id = nouvelle_reservation()

    modifies = enregistrer_fiche(
        reservation_id,
        reception,
        {
            "nom": "LE CLOEREC",
            "pays": "France",
            "partenaire": "  Booking.com ",
            "notes": "arrivé : 19h20",
        },
    )

    assert modifies == ["Pays de nat.", "Partenaire", "Notes"]
    fiche = fiche_sejour(reservation_id)
    assert fiche["client"]["pays"] == "France"
    assert fiche["reservation"]["partenaire"] == "Booking.com"
    assert fiche["reservation"]["notes"] == "arrivé : 19h20"
    assert [(note["description"], note["auteur"]) for note in fiche["historique"]] == [
        ("Fiche modifiée : Pays de nat., Partenaire, Notes", "Réception")
    ]


def test_enregistrer_fiche_sans_changement_ne_journalise_rien(reception: int) -> None:
    reservation_id = nouvelle_reservation()
    enregistrer_fiche(reservation_id, reception, {"partenaire": "Expedia"})

    assert enregistrer_fiche(reservation_id, reception, {"partenaire": "Expedia "}) == []
    assert descriptions(reservation_id) == ["Fiche modifiée : Partenaire"]


def test_notes_client_partagees_et_independantes_des_notes_reservation(reception: int) -> None:
    client_id = creer_client("LE CLOEREC", notes="Note client initiale")
    premiere = creer_reservation(client_id)
    seconde = creer_reservation(client_id)

    assert fiche_sejour(premiere)["client"]["notes_client"] == "Note client initiale"
    assert enregistrer_fiche(premiere, reception, {"notes": "Séjour", "notes_client": "Préférence"}) == [
        "Notes",
        "Notes Client",
    ]
    assert fiche_sejour(premiere)["reservation"]["notes"] == "Séjour"
    assert fiche_sejour(seconde)["reservation"]["notes"] is None
    assert fiche_sejour(seconde)["client"]["notes_client"] == "Préférence"
    assert enregistrer_fiche(premiere, reception, {"notes_client": " Préférence "}) == []
    assert descriptions(premiere) == ["Fiche modifiée : Notes, Notes Client"]


def test_enregistrer_fiche_refuse_un_nom_vide(base) -> None:
    reservation_id = nouvelle_reservation()

    with pytest.raises(FicheInvalide):
        enregistrer_fiche(reservation_id, None, {"nom": "  "})
    assert fiche_sejour(reservation_id)["client"]["nom"] == "LE CLOEREC"


def _client(reservation_id: int) -> dict:
    return fiche_sejour(reservation_id)["client"]


def test_creer_reservation_sans_client_reutilise_client_passage(base) -> None:
    premiere = creer_reservation()
    seconde = creer_reservation()

    assert _client(premiere)["nom"] == NOM_CLIENT_PASSAGE
    assert _client(premiere)["id"] == _client(seconde)["id"]
    assert premiere != seconde
    assert _client(premiere)["telephone"] is None


def test_creer_client_passage_ne_duplique_pas_et_n_ecrit_pas_ses_coordonnees(base) -> None:
    premiere = creer_reservation()
    identifiant = _client(premiere)["id"]

    assert creer_client(" CLIENT PASSAGE ", telephone="0600000000", pays="France") == identifiant
    assert [client["id"] for client in lister_clients() if client["nom"] == NOM_CLIENT_PASSAGE] == [identifiant]
    assert _client(premiere)["telephone"] is None
    assert _client(premiere)["pays"] is None


def test_client_passage_protege_ses_coordonnees_et_garde_la_reservation(reception: int) -> None:
    reservation_id = creer_reservation()

    with pytest.raises(FicheInvalide, match="CLIENT PASSAGE"):
        enregistrer_fiche(reservation_id, reception, {"nom": "MARTIN", "telephone": "0600000000"})
    assert _client(reservation_id)["nom"] == NOM_CLIENT_PASSAGE
    assert _client(reservation_id)["telephone"] is None

    assert enregistrer_fiche(reservation_id, reception, {"partenaire": "Direct", "nom": NOM_CLIENT_PASSAGE}) == [
        "Partenaire"
    ]
    assert fiche_sejour(reservation_id)["reservation"]["partenaire"] == "Direct"
    with pytest.raises(FicheInvalide, match="réservé"):
        enregistrer_fiche(reservation_id, reception, {"nom": NOM_CLIENT_PASSAGE}, client_id=creer_client("MARTIN"))


def test_reassocier_journalise_et_ecrit_sur_le_nouveau_client(reception: int) -> None:
    ancien = creer_client("LE CLOEREC", telephone="01", notes="Fidèle", pays="France")
    nouveau = creer_client("MARTIN", telephone="02", notes="Calme", pays="Espagne")
    reservation_id = creer_reservation(ancien)
    passage_id = _client(creer_reservation())["id"]

    assert enregistrer_fiche(reservation_id, reception, {}, client_id=nouveau) == ["Client"]
    assert descriptions(reservation_id) == ["Fiche modifiée : Client"]
    assert _client(reservation_id)["id"] == nouveau
    assert _client(creer_reservation(ancien))["telephone"] == "01"
    assert _client(creer_reservation(ancien))["notes_client"] == "Fidèle"

    assert enregistrer_fiche(
        reservation_id,
        reception,
        {"nom": "MARTIN", "telephone": "0999", "notes_client": "Calme", "pays": "Espagne"},
        client_id=nouveau,
    ) == ["Téléphone"]
    assert _client(reservation_id)["telephone"] == "0999"
    assert _client(creer_reservation(ancien))["telephone"] == "01"

    with pytest.raises(FicheInvalide, match="introuvable"):
        enregistrer_fiche(reservation_id, reception, {"notes": "secrète"}, client_id=999999)
    assert fiche_sejour(reservation_id)["reservation"]["notes"] is None
    assert _client(reservation_id)["id"] == nouveau

    with pytest.raises(FicheInvalide, match="CLIENT PASSAGE"):
        enregistrer_fiche(reservation_id, reception, {"telephone": "0999", "nom": "MARTIN"}, client_id=passage_id)
    assert _client(reservation_id)["id"] == nouveau
    assert _client(creer_reservation())["telephone"] is None

    assert enregistrer_fiche(
        reservation_id,
        reception,
        {"nom": NOM_CLIENT_PASSAGE, "telephone": "", "notes_client": "", "pays": ""},
        client_id=passage_id,
    ) == ["Client"]
    assert _client(reservation_id)["id"] == passage_id
    assert _client(creer_reservation(nouveau))["telephone"] == "0999"


def test_recherche_clients_ignore_casse_et_accents_et_classe_les_proches(base) -> None:
    eleonore = creer_client("Éléonore")
    martin = creer_client("MARTIN", telephone="01")
    homonyme = creer_client("MARTIN", telephone="02")
    martine = creer_client("Martine Dupont", email="martine@hotel.fr")
    dupond = creer_client("Dupond")
    clerc = creer_client("LE CLERC")
    zorro = creer_client("ZORRO")

    assert [client["id"] for client in rechercher_clients("  éléonore ")] == [eleonore]
    assert [client["id"] for client in rechercher_clients("ELEONORE")] == [eleonore]
    assert [client["nom"] for client in rechercher_clients("martin")] == ["MARTIN", "MARTIN", "Martine Dupont"]
    assert [client["id"] for client in rechercher_clients("martin") if client["nom"] == "MARTIN"] == sorted(
        (martin, homonyme)
    )
    libelles = [libelle_client(client) for client in rechercher_clients("MARTIN") if client["nom"] == "MARTIN"]
    assert libelles == [f"MARTIN · 01 · n° {martin}", f"MARTIN · 02 · n° {homonyme}"]

    proches = [client["nom"] for client in rechercher_clients("dupont")]
    assert proches[0] == "Martine Dupont"
    assert "Dupond" in proches
    assert "ZORRO" not in proches
    assert [client["id"] for client in rechercher_clients("leclerc")] == [clerc]

    vide = rechercher_clients("   ")
    assert {client["id"] for client in vide} == {eleonore, martin, homonyme, martine, dupond, clerc, zorro}
    assert vide == sorted(vide, key=lambda client: (normaliser_nom(client["nom"]), client["id"]))


def _identite() -> IdentiteFacturation:
    return IdentiteFacturation(
        nom_commercial="Hôtel Panorama",
        denomination="Panorama SAS",
        forme_juridique=FormeJuridique.sas,
        capital_centimes=1_000_000,
        adresse_siege="1 quai du Port\n29200 Brest",
        adresse_facturation=None,
        siren="123456789",
        siret="12345678900012",
        immatriculation="RCS Brest",
        numero_tva="FR12123456789",
        regime_tva=RegimeTVA.assujetti,
        taux_hebergement_pour_mille=100,
        delai_paiement_jours=0,
        conditions_paiement=None,
        escompte=None,
        penalites=None,
    )


def test_facturer_numerote_a_la_suite_une_seule_fois(reception: int) -> None:
    enregistrer_identite(_identite())
    premiere = creer_reservation(creer_client("LE CLOEREC", adresse="1 rue du Port, 29200 Brest"))
    seconde = creer_reservation(creer_client("MARTIN", adresse="2 rue du Port, 29200 Brest"))
    with get_session() as session:
        for reservation_id, nom in ((premiere, "LE CLOEREC"), (seconde, "MARTIN")):
            reservation = session.get(Reservation, reservation_id)
            reservation.facturation = nom
            session.add(reservation)
        session.commit()

    assert facturer(premiere, reception) == 1
    assert facturer(seconde, reception) == 2
    assert facturer(premiere, reception) == 1

    fiche = fiche_sejour(premiere)
    assert fiche["reservation"]["numero_facture"] == 1
    assert fiche["reservation"]["date_facture"] == date.today()
    assert descriptions(premiere) == ["Facture n° 1 émise"]


def test_facturer_refuse_une_reservation_annulee(reception: int) -> None:
    reservation_id = nouvelle_reservation()
    annuler_reservation(reservation_id, reception)

    with pytest.raises(FacturationImpossible):
        facturer(reservation_id, reception)
    assert fiche_sejour(reservation_id)["reservation"]["numero_facture"] is None


def test_la_fiche_compte_et_totalise_comme_la_capture(reception: int) -> None:
    reservation_id = nouvelle_reservation()
    type_id = creer_type_chambre("Single BB")
    chambre_id = creer_chambre("406", 406, type_chambre_id=type_id)
    ajouter_sejour(reservation_id, chambre_id, ARRIVEE, DEPART, prix_nuit_centimes=6882, user_id=reception)
    ajouter_consommation(reservation_id, "Petit-déjeuner", 1, 1400, reception)
    ajouter_reglement(reservation_id, ModeReglement.ota, 13764, reception)

    fiche = fiche_sejour(reservation_id)

    assert fiche["statut_sejour"] == StatutReservation.confirmee
    assert (fiche["debut"], fiche["fin"]) == (ARRIVEE, DEPART)
    [ligne] = fiche["lignes"]
    assert (ligne["type_chambre"], ligne["chambre_nom"], ligne["nuits"]) == ("Single BB", "406", 2)
    assert (ligne["adultes"], ligne["enfants"], ligne["taxe"], ligne["montant"]) == (1, 0, 400, 13764)
    assert fiche["compteurs"] == {
        "reservations": 1,
        "consommations": 1,
        "reglements": 1,
        "modifications": 3,
    }
    assert fiche["totaux"].total == 13764 + 400 + 1400
    assert fiche["totaux"].solde == 1800
    assert descriptions(reservation_id) == [
        "Règlement OTA (prépayé) : 137,64\u00a0€",
        "Consommation ajoutée : 1 × Petit-déjeuner (14,00\u00a0€)",
        "Séjour ajouté : chambre 406 du 18/10/2026 au 20/10/2026",
    ]
    [ligne_liste] = lister_reservations()
    assert (ligne_liste["chambres"], ligne_liste["nuits"], ligne_liste["total"]) == ("406", 2, 15564)
    assert ligne_liste["statut"] == StatutReservation.confirmee


def test_modifier_puis_supprimer_une_ligne(reception: int) -> None:
    reservation_id = nouvelle_reservation()
    chambre_id = creer_chambre("406", 406)
    autre_id = creer_chambre("407", 407)
    sejour_id = ajouter_sejour(reservation_id, chambre_id, ARRIVEE, DEPART, user_id=reception)
    ajouter_sejour(nouvelle_reservation(), autre_id, ARRIVEE, DEPART)

    with pytest.raises(ChambreOccupee):
        modifier_sejour(sejour_id, autre_id, ARRIVEE, DEPART, 1, 0, 6882, None, reception)

    modifier_sejour(sejour_id, chambre_id, ARRIVEE, date(2026, 10, 21), 2, 1, 6882, "M. Martin", reception)
    [ligne] = fiche_sejour(reservation_id)["lignes"]
    assert (ligne["nuits"], ligne["adultes"], ligne["enfants"]) == (3, 2, 1)
    assert ligne["nom_client"] == "M. Martin"
    assert ligne["montant"] == 20646  # 3 × 68,82 €
    assert ligne["taxe"] == 1200  # l'enfant est exonéré

    supprimer_sejour(sejour_id, reception)
    fiche = fiche_sejour(reservation_id)
    assert fiche["lignes"] == []
    assert descriptions(reservation_id)[:2] == [
        "Séjour supprimé : chambre 406 du 18/10/2026 au 21/10/2026",
        "Séjour modifié : chambre 406 du 18/10/2026 au 21/10/2026",
    ]


def test_annuler_journalise_une_seule_fois(reception: int) -> None:
    reservation_id = nouvelle_reservation()

    annuler_reservation(reservation_id, reception)
    annuler_reservation(reservation_id, reception)

    fiche = fiche_sejour(reservation_id)
    assert fiche["statut_sejour"] == StatutReservation.annulee
    assert descriptions(reservation_id) == ["Réservation annulée"]


def test_le_statut_choisi_se_relit(reception: int) -> None:
    reservation_id = nouvelle_reservation()

    libelles = enregistrer_fiche(reservation_id, reception, {"statut": "parti"})

    assert libelles == ["Statut"]
    assert fiche_sejour(reservation_id)["statut_sejour"] == StatutReservation.parti
    assert lister_reservations()[0]["statut"] == StatutReservation.parti


def test_un_statut_inconnu_est_refuse(reception: int) -> None:
    reservation_id = nouvelle_reservation()

    with pytest.raises(FicheInvalide):
        enregistrer_fiche(reservation_id, reception, {"statut": "a_venir"})

    assert fiche_sejour(reservation_id)["statut_sejour"] == StatutReservation.confirmee


def test_l_occupant_se_relit(reception: int) -> None:
    reservation_id = nouvelle_reservation()

    libelles = enregistrer_fiche(reservation_id, reception, {"nom_occupant": "LE CLOEREC Benedicte"})

    fiche = fiche_sejour(reservation_id)
    assert libelles == ["Occupant"]
    assert fiche["reservation"]["nom_occupant"] == "LE CLOEREC Benedicte"
    assert lister_reservations()[0]["client"] == "LE CLOEREC Benedicte"


def test_reprendre_refuse_une_chambre_deja_reprise(reception: int) -> None:
    reservation_id = nouvelle_reservation()
    chambre_id = creer_chambre("406", 406)
    ajouter_sejour(reservation_id, chambre_id, ARRIVEE, DEPART, user_id=reception)
    annuler_reservation(reservation_id, reception)
    autre = nouvelle_reservation()
    ajouter_sejour(autre, chambre_id, ARRIVEE, DEPART, user_id=reception)

    with pytest.raises(ChambreOccupee):
        reprendre_reservation(reservation_id, reception)

    assert fiche_sejour(reservation_id)["statut_sejour"] == StatutReservation.annulee


def test_renommer_un_type_change_le_libelle_relu_par_la_fiche(reception: int) -> None:
    reservation_id = nouvelle_reservation()
    type_id = creer_type_chambre("Single BB")
    chambre_id = creer_chambre("406", 406, type_chambre_id=type_id)
    ajouter_sejour(reservation_id, chambre_id, ARRIVEE, DEPART, user_id=reception)

    assert fiche_sejour(reservation_id)["lignes"][0]["type_chambre"] == "Single BB"
    assert renommer_type_chambre(type_id, " Suite ") is True
    assert fiche_sejour(reservation_id)["lignes"][0]["type_chambre"] == "Suite"
    assert renommer_type_chambre(type_id, "Suite") is False
    assert fiche_sejour(reservation_id)["lignes"][0]["type_chambre"] == "Suite"


def test_une_occupation_modifiee_reste_partagee(base) -> None:
    occupation_id = creer_occupation_chambre(2, "Twin")
    creer_chambre("406", 406, occupation_chambre_id=occupation_id)
    creer_chambre("407", 407, occupation_chambre_id=occupation_id)

    assert modifier_occupation_chambre(occupation_id, 3, " Triple ") is True
    assert modifier_occupation_chambre(occupation_id, 3, "Triple") is False

    ecran = ecran_parametres()
    assert ecran["occupations"] == [{"id": occupation_id, "nombre_personnes": 3, "type_lits": "Triple"}]
    liens = {chambre["nom"]: chambre["occupation_chambre_id"] for chambre in ecran["chambres"]}
    assert liens == {"406": occupation_id, "407": occupation_id}


def test_supprimer_un_catalogue_utilise_est_refuse(base) -> None:
    type_id = creer_type_chambre("Double")
    occupation_id = creer_occupation_chambre(2, "Twin")
    creer_chambre("101", 1, type_chambre_id=type_id, occupation_chambre_id=occupation_id)

    with pytest.raises(CatalogueInvalide, match="Ce type est utilisé par une chambre"):
        supprimer_type_chambre(type_id)
    with pytest.raises(CatalogueInvalide, match="Cette occupation est utilisée par une chambre"):
        supprimer_occupation_chambre(occupation_id)

    ecran = ecran_parametres()
    assert ecran["types"] == [_type("Double", type_id)]
    assert ecran["chambres"][0]["type_chambre_id"] == type_id
    assert ecran["chambres"][0]["occupation_chambre_id"] == occupation_id


def _type(libelle: str, type_id: int, **champs) -> dict:
    return {
        "id": type_id,
        "wubook_id": None,
        "libelle": libelle,
        "description": "",
        "nom_raccourci": None,
        "prix_defaut": 0.0,
        "prix_mini": 0.0,
        "channel_manager_uniquement": False,
        "virtuelles": [],
        **champs,
    }


def test_le_type_enregistre_raccourci_prix_et_channel(base) -> None:
    type_id = creer_type_chambre(
        "Double",
        nom_raccourci=" 2b ",
        prix_defaut=85,
        prix_mini=50,
        channel_manager_uniquement=True,
    )
    assert ecran_parametres()["types"] == [
        _type("Double", type_id, nom_raccourci="2b", prix_defaut=85.0, prix_mini=50.0, channel_manager_uniquement=True)
    ]

    assert enregistrer_type_chambre(type_id, "Double", "2b", 85, 50, True) is False
    assert enregistrer_type_chambre(type_id, "Double", "", 90.5, 0, False) is True
    assert ecran_parametres()["types"] == [_type("Double", type_id, prix_defaut=90.5)]

    with pytest.raises(CatalogueInvalide, match="Le nom raccourci tient sur 4 caractères"):
        creer_type_chambre("Suite", nom_raccourci="SUITE")
    with pytest.raises(CatalogueInvalide, match="Le prix ne peut pas être négatif"):
        creer_type_chambre("Suite", prix_mini=-1)
    creer_type_chambre("Suite", nom_raccourci="STE")
    with pytest.raises(CatalogueInvalide, match="Ce nom raccourci existe déjà"):
        enregistrer_type_chambre(type_id, "Double", "STE", 90.5, 0, False)


def _virtuelle(
    raccourci: str, virtuelle_id: int, prix_defaut: float = 0.0, prix_mini: float = 0.0, description: str = ""
) -> dict:
    return {
        "id": virtuelle_id,
        "wubook_id": None,
        "description": description,
        "nom_raccourci": raccourci,
        "prix_defaut": prix_defaut,
        "prix_mini": prix_mini,
    }


def test_chambre_virtuelle_du_catalogue(base) -> None:
    type_id = creer_type_chambre("Double", nom_raccourci="2B")
    autre_id = creer_type_chambre("Suite")

    with pytest.raises(CatalogueInvalide, match="Ce type est introuvable"):
        creer_chambre_virtuelle(0, "V1", 10, 5)
    with pytest.raises(CatalogueInvalide, match="Le nom raccourci est obligatoire"):
        creer_chambre_virtuelle(type_id, "  ", 10, 5)
    with pytest.raises(CatalogueInvalide, match="Le nom raccourci tient sur 4 caractères"):
        creer_chambre_virtuelle(type_id, "SUITE", 10, 5)
    with pytest.raises(CatalogueInvalide, match="Le prix est obligatoire"):
        creer_chambre_virtuelle(type_id, "V1", None, 5)
    with pytest.raises(CatalogueInvalide, match="Le prix est obligatoire"):
        creer_chambre_virtuelle(type_id, "V1", 10, "")
    with pytest.raises(CatalogueInvalide, match="Le prix ne peut pas être négatif"):
        creer_chambre_virtuelle(type_id, "V1", -1, 0)

    premiere = creer_chambre_virtuelle(type_id, " b ", 0, 40)
    seconde = creer_chambre_virtuelle(type_id, "a", 85.5, 50)
    assert creer_chambre_virtuelle(autre_id, "2B", 12, 0) > 0
    with pytest.raises(CatalogueInvalide, match="Ce nom raccourci existe déjà"):
        creer_chambre_virtuelle(autre_id, "a", 1, 1)
    with pytest.raises(CatalogueInvalide, match="Ce type est utilisé par une chambre virtuelle"):
        supprimer_type_chambre(type_id)

    assert enregistrer_chambre_virtuelle(premiere, "b", 0, 40) is False
    assert enregistrer_chambre_virtuelle(premiere, "c", 12.5, 0) is True
    with pytest.raises(CatalogueInvalide, match="Ce nom raccourci existe déjà"):
        enregistrer_chambre_virtuelle(premiere, "a", 12.5, 0)
    with pytest.raises(CatalogueInvalide, match="Cette chambre virtuelle est introuvable"):
        enregistrer_chambre_virtuelle(0, "z", 1, 1)

    types = {ligne["libelle"]: ligne for ligne in ecran_parametres()["types"]}
    assert types["Double"]["virtuelles"] == [
        _virtuelle("a", seconde, 85.5, 50.0),
        _virtuelle("c", premiere, 12.5, 0.0),
    ]
    assert types["Suite"]["virtuelles"][0]["nom_raccourci"] == "2B"

    supprimer_chambre_virtuelle(premiere)
    supprimer_chambre_virtuelle(seconde)
    with pytest.raises(CatalogueInvalide, match="Cette chambre virtuelle est introuvable"):
        supprimer_chambre_virtuelle(premiere)
    assert ecran_parametres()["types"][0]["virtuelles"] == []
    supprimer_type_chambre(type_id)


def test_les_descriptions_se_modifient_et_peuvent_etre_effacees(base) -> None:
    type_id = creer_type_chambre("Double")
    virtuelle_id = creer_chambre_virtuelle(type_id, "V1", 80, 50, description=" Avec petit déjeuner ")
    assert enregistrer_type_chambre(type_id, "Double", "", 80, 50, False, description=" Avec balcon ") is True
    assert enregistrer_type_chambre(type_id, "Double", "", 80, 50, False, description="Avec balcon") is False
    assert enregistrer_type_chambre(type_id, "Double", "", 90, 50, False) is True
    assert enregistrer_chambre_virtuelle(virtuelle_id, "V1", 80, 50, description="Avec petit déjeuner") is False
    assert enregistrer_chambre_virtuelle(virtuelle_id, "V1", 90, 50) is True
    type_chambre = ecran_parametres()["types"][0]
    assert type_chambre["description"] == "Avec balcon"
    assert type_chambre["virtuelles"][0]["description"] == "Avec petit déjeuner"
    assert enregistrer_chambre_virtuelle(virtuelle_id, "V1", 90, 50, description=" Vue mer ") is True
    assert ecran_parametres()["types"][0]["virtuelles"][0]["description"] == "Vue mer"
    assert enregistrer_type_chambre(type_id, "Double", "", 90, 50, False, description="") is True
    assert enregistrer_chambre_virtuelle(virtuelle_id, "V1", 90, 50, description="") is True
    type_chambre = ecran_parametres()["types"][0]
    assert type_chambre["description"] == type_chambre["virtuelles"][0]["description"] == ""


def test_l_etage_se_modifie_sans_changer_les_affectations(base) -> None:
    type_id = creer_type_chambre("Double")
    occupation_id = creer_occupation_chambre(2, "Twin")
    chambre_id = creer_chambre("101", 1, type_chambre_id=type_id, occupation_chambre_id=occupation_id, etage=2)
    assert ecran_parametres()["chambres"][0]["etage"] == 2
    assert modifier_etage_chambre(chambre_id, 2) is False
    assert modifier_etage_chambre(chambre_id, -1) is True
    chambre = ecran_parametres()["chambres"][0]
    assert chambre["etage"] == -1
    assert (chambre["type_chambre_id"], chambre["occupation_chambre_id"]) == (type_id, occupation_id)
    assert modifier_etage_chambre(chambre_id, 0) is True
    with pytest.raises(CatalogueInvalide, match="Cette chambre est introuvable"):
        modifier_etage_chambre(0, 1)


@pytest.mark.parametrize("etage", [None, "", "2", 1.5, True, float("nan"), float("inf")])
def test_un_etage_non_entier_est_refuse(base, etage) -> None:
    chambre_id = creer_chambre("101", 1, etage=2)
    with pytest.raises(CatalogueInvalide, match="L'étage doit être un nombre entier"):
        modifier_etage_chambre(chambre_id, etage)
    with pytest.raises(CatalogueInvalide, match="L'étage doit être un nombre entier"):
        creer_chambre("102", 2, etage=etage)
    assert [chambre["etage"] for chambre in ecran_parametres()["chambres"]] == [2]


def test_le_catalogue_refuse_le_vide_et_le_doublon(base) -> None:
    with pytest.raises(CatalogueInvalide, match="Le libellé est obligatoire"):
        creer_type_chambre("  ")
    type_id = creer_type_chambre("Double")
    with pytest.raises(CatalogueInvalide, match="Ce type existe déjà"):
        creer_type_chambre("Double")
    autre_id = creer_type_chambre("double")
    assert autre_id != type_id

    with pytest.raises(CatalogueInvalide, match="Le nombre de personnes doit être au moins 1"):
        creer_occupation_chambre(0, "Twin")
    with pytest.raises(CatalogueInvalide, match="Le type de lits est obligatoire"):
        creer_occupation_chambre(2, "  ")
    creer_occupation_chambre(2, "Twin")
    with pytest.raises(CatalogueInvalide, match="Cette occupation existe déjà"):
        creer_occupation_chambre(2, " Twin ")


def test_creer_chambre_prend_les_identifiants_en_mot_cle(base) -> None:
    type_id = creer_type_chambre("Single BB")
    occupation_id = creer_occupation_chambre(1, "Single")

    with pytest.raises(TypeError):
        creer_chambre("406", 406, type_id)

    chambre_id = creer_chambre("406", 406, type_chambre_id=type_id, occupation_chambre_id=occupation_id)
    chambre = ecran_parametres()["chambres"][0]
    assert chambre["id"] == chambre_id
    assert chambre["type_chambre"] == "Single BB"
    assert chambre["type_chambre_id"] == type_id
    assert chambre["occupation_chambre_id"] == occupation_id
    assert attribuer_type_chambre(chambre_id, type_id) is False
    assert attribuer_type_chambre(chambre_id, None) is True
    assert ecran_parametres()["chambres"][0]["type_chambre"] is None
    assert ecran_parametres()["position"] == 407
