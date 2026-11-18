import asyncio
from datetime import UTC, date, timedelta

from nicegui import ui
from nicegui.testing import User

from ma_receptionniste.auth import EmailDejaUtilise, register_user
from ma_receptionniste.consultations import ecran_parametres, fiche_sejour, lister_clients, lister_produits
from ma_receptionniste.db import get_session
from ma_receptionniste.saisie import (
    NOM_CLIENT_PASSAGE,
    ajouter_sejour,
    creer_chambre,
    creer_client,
    creer_produit,
    creer_reservation,
    creer_type_chambre,
    definir_produit_actif,
)

EMAIL = "fiche@hotel-panorama.fr"
MOT_DE_PASSE = "panorama-fiche"


def _type_single_bb() -> int:
    connus = {ligne["libelle"]: ligne["id"] for ligne in ecran_parametres()["types"]}
    if "Single BB" in connus:
        return connus["Single BB"]
    return creer_type_chambre("Single BB")


def _reservation_de_la_capture() -> int:
    with get_session() as session:
        try:
            register_user(session, EMAIL, "Réception", MOT_DE_PASSE)
        except EmailDejaUtilise:
            pass
    reservation_id = creer_reservation(creer_client("LE CLOEREC", pays="France"))
    hier = date.today() - timedelta(days=1)
    chambre_id = creer_chambre(f"406-{reservation_id}", 1, type_chambre_id=_type_single_bb())
    ajouter_sejour(reservation_id, chambre_id, hier, hier + timedelta(days=2), prix_nuit_centimes=6882)
    return reservation_id


async def test_la_fiche_montre_la_ligne_les_actions_et_le_total(user: User) -> None:
    reservation_id = _reservation_de_la_capture()

    await user.open("/login")
    user.find("Email").type(EMAIL)
    user.find("Mot de passe").type(MOT_DE_PASSE)
    user.find("Se connecter").click()
    await user.should_see("Aujourd'hui", retries=30)

    await user.open(f"/reservations/{reservation_id}")
    await user.should_see("LE CLOEREC")
    await user.should_see("Réservations (1)")
    await user.should_see("Facturer")
    await user.should_see("Notes Client")
    # 2 nuits à 68,82 € et 2 nuits de taxe à 2,00 € pour un adulte.
    await user.should_see("141,64\u00a0€")


async def test_ajouter_une_ligne_s_inscrit_dans_le_tableau(user: User) -> None:
    reservation_id = _reservation_de_la_capture()

    await user.open("/login")
    user.find("Email").type(EMAIL)
    user.find("Mot de passe").type(MOT_DE_PASSE)
    user.find("Se connecter").click()
    await user.should_see("Aujourd'hui", retries=30)

    await user.open(f"/reservations/{reservation_id}")
    user.find("Ajouter une nouvelle ligne").click()
    await user.should_not_see("Ajouter une nouvelle ligne", retries=20)
    await user.should_see("Enregistrer")
    await user.should_not_see("Nouvelle ligne de séjour")


async def _ouvrir_session(user: User, email: str) -> None:
    with get_session() as session:
        try:
            register_user(session, email, "Réception", MOT_DE_PASSE)
        except EmailDejaUtilise:
            pass
    await user.open("/login")
    user.find("Email").type(email)
    user.find("Mot de passe").type(MOT_DE_PASSE)
    user.find("Se connecter").click()
    await user.should_see("Aujourd'hui", retries=30)


def _champ(user: User, marker: str):
    return next(iter(user.find(marker=marker).elements))


async def _ligne_consommation(
    reservation_id: int, *, prix_unitaire_centimes: int | None = None, jour: date | None = None
) -> dict:
    for _ in range(40):
        ligne = fiche_sejour(reservation_id)["consommations"][0]
        moment = ligne["date"]
        affiche = (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).astimezone().date()
        prix_ok = prix_unitaire_centimes is None or ligne["prix_unitaire_centimes"] == prix_unitaire_centimes
        if prix_ok and (jour is None or affiche == jour):
            return ligne
        await asyncio.sleep(0.05)
    raise AssertionError(fiche_sejour(reservation_id)["consommations"][0])


async def test_nouvelle_reservation_ouvre_directement_client_passage(user: User) -> None:
    await _ouvrir_session(user, "passage-menu@hotel-panorama.fr")
    user.find("Nouvelle réservation").click()
    await user.should_see("Fiche séjour", retries=30)
    await user.should_see(NOM_CLIENT_PASSAGE)
    assert _champ(user, "nom-client").value == NOM_CLIENT_PASSAGE
    assert _champ(user, "nom-client").enabled is False
    assert _champ(user, "telephone-client").enabled is False
    assert _champ(user, "notes-client").enabled is False

    await user.open("/reservations")
    await user.should_not_see("Ajoutez un client avant de créer une réservation.")
    user.find(marker="creer-reservation").click()
    await user.should_see("Fiche séjour", retries=30)
    assert _champ(user, "nom-client").value == NOM_CLIENT_PASSAGE
    assert _champ(user, "telephone-client").enabled is False


async def test_selection_charge_les_coordonnees_et_confirme_sans_perdre_le_brouillon(user: User) -> None:
    await _ouvrir_session(user, "selection-client@hotel-panorama.fr")
    ancien = creer_client("LE CLOEREC", pays="France", telephone="0102030405")
    martin = creer_client(
        "ZÉPHYRIN",
        telephone="0611223344",
        email="zephyrin@hotel.fr",
        pays="Espagne",
        adresse="2 rue des Pins",
        notes="Calme",
    )
    reservation_id = creer_reservation(ancien)
    chambre_id = creer_chambre(f"406-{reservation_id}", 1, type_chambre_id=_type_single_bb())
    ajouter_sejour(reservation_id, chambre_id, date.today(), date.today() + timedelta(days=2))

    await user.open(f"/reservations/{reservation_id}")
    await user.should_see("LE CLOEREC")
    await user.should_see(f"406-{reservation_id}")
    user.find(marker="partenaire-reservation").type("Expedia")
    user.find(marker="occupant-reservation").type("Bénédicte")
    user.find(marker="client-sejour").click()
    user.find(marker="recherche-client").type("zephyrin")
    await user.should_see("0611223344", retries=20)
    user.find(marker=f"resultat-client-{martin}").click()

    assert _champ(user, "nom-client").value == "ZÉPHYRIN"
    assert _champ(user, "pays-client").value == "Espagne"
    assert _champ(user, "telephone-client").value == "0611223344"
    assert _champ(user, "telephone-client").enabled is True
    assert _champ(user, "email-client").value == "zephyrin@hotel.fr"
    assert _champ(user, "adresse-client").value == "2 rue des Pins"
    assert _champ(user, "notes-client").value == "Calme"
    assert _champ(user, "partenaire-reservation").value == "Expedia"
    assert _champ(user, "occupant-reservation").value == "Bénédicte"
    await user.should_see(f"406-{reservation_id}")
    assert fiche_sejour(reservation_id)["client"]["id"] == ancien

    user.find("Confirmer").click()
    await user.should_see("Fiche enregistrée", retries=20)
    fiche = fiche_sejour(reservation_id)
    assert fiche["client"]["id"] == martin
    assert fiche["client"]["telephone"] == "0611223344"
    assert fiche["client"]["notes_client"] == "Calme"
    assert fiche["reservation"]["partenaire"] == "Expedia"
    assert fiche["reservation"]["nom_occupant"] == "Bénédicte"
    assert fiche["lignes"][0]["chambre_nom"] == f"406-{reservation_id}"
    assert next(client["telephone"] for client in lister_clients() if client["id"] == ancien) == "0102030405"


async def test_abandon_garde_le_client_initial(user: User) -> None:
    await _ouvrir_session(user, "abandon-client@hotel-panorama.fr")
    ancien = creer_client("LE CLOEREC", pays="France")
    martin = creer_client("ZÉPHYRIN ABANDON", telephone="0699001122")
    reservation_id = creer_reservation(ancien)

    await user.open(f"/reservations/{reservation_id}")
    await user.should_see("LE CLOEREC")
    user.find(marker="client-sejour").click()
    user.find(marker="recherche-client").type("abandon")
    await user.should_see("0699001122", retries=20)
    user.find(marker=f"resultat-client-{martin}").click()
    assert _champ(user, "nom-client").value == "ZÉPHYRIN ABANDON"
    user.find("Abandon").click()
    await user.should_see("Abandonner les modifications ?", retries=10)
    user.find(kind=ui.button, content="Abandonner").click()
    await user.should_see("Aujourd'hui", retries=30)

    await user.open(f"/reservations/{reservation_id}")
    await user.should_see("LE CLOEREC")
    assert _champ(user, "nom-client").value == "LE CLOEREC"
    assert fiche_sejour(reservation_id)["client"]["id"] == ancien


async def test_plus_cree_le_client_tout_de_suite_et_abandon_le_conserve(user: User) -> None:
    await _ouvrir_session(user, "plus-client@hotel-panorama.fr")
    ancien = creer_client("LE CLOEREC", pays="France")
    reservation_id = creer_reservation(ancien)

    await user.open(f"/reservations/{reservation_id}")
    await user.should_see("LE CLOEREC")
    user.find(marker="partenaire-reservation").type("Direct")
    user.find(marker="client-sejour").click()
    assert _champ(user, "creer-client").enabled is False
    user.find(marker="recherche-client").type("DURAND PLUS")
    await user.should_see("Aucun client ne correspond", retries=20)
    assert _champ(user, "creer-client").enabled is True
    user.find(marker="creer-client").click()
    await user.should_see("Client créé", retries=20)
    assert _champ(user, "nom-client").value == "DURAND PLUS"
    assert _champ(user, "telephone-client").enabled is True
    assert _champ(user, "telephone-client").value == ""
    assert _champ(user, "partenaire-reservation").value == "Direct"
    user.find(marker="telephone-client").type("0677889900")
    user.find("Abandon").click()
    await user.should_see("Abandonner les modifications ?", retries=10)
    user.find(kind=ui.button, content="Abandonner").click()
    await user.should_see("Aujourd'hui", retries=30)

    cree = next(client for client in lister_clients() if client["nom"] == "DURAND PLUS")
    assert cree["telephone"] is None
    assert fiche_sejour(reservation_id)["client"]["id"] == ancien
    assert fiche_sejour(reservation_id)["reservation"]["partenaire"] is None

    await user.open(f"/reservations/{reservation_id}")
    await user.should_see("LE CLOEREC")
    user.find(marker="client-sejour").click()
    user.find(marker="recherche-client").type("DURAND PLUS")
    await user.should_see(f"resultat-client-{cree['id']}", retries=20)
    user.find(marker=f"resultat-client-{cree['id']}").click()
    assert _champ(user, "nom-client").value == "DURAND PLUS"
    assert _champ(user, "partenaire-reservation").value == ""
    user.find(marker="telephone-client").type("0677889900")
    user.find("Confirmer").click()
    await user.should_see("Fiche enregistrée", retries=20)
    fiche = fiche_sejour(reservation_id)
    assert fiche["client"]["id"] == cree["id"]
    assert fiche["client"]["telephone"] == "0677889900"


async def test_la_loupe_pre_remplit_la_recherche_avec_l_occupant(user: User) -> None:
    await _ouvrir_session(user, "loupe-occupant@hotel-panorama.fr")
    connu = creer_client("ZÉPHYRIN LOUPE", telephone="0610101010")
    ancien = creer_client("LE CLOEREC")
    reservation_id = creer_reservation(ancien)

    await user.open(f"/reservations/{reservation_id}")
    await user.should_see("LE CLOEREC")
    user.find(marker="loupe-occupant").click()
    assert not (_champ(user, "recherche-client").value or "").strip()
    assert _champ(user, "creer-client").enabled is False
    await user.should_see(f"resultat-client-{connu}", retries=20)

    user.find(marker="occupant-reservation").type("  ZÉPHYRIN LOUPE  ")
    user.find(marker="loupe-occupant").click()
    assert _champ(user, "recherche-client").value == "ZÉPHYRIN LOUPE"
    assert _champ(user, "occupant-reservation").value == "  ZÉPHYRIN LOUPE  "
    await user.should_see("0610101010", retries=20)
    await user.should_not_see(f"resultat-client-{ancien}", retries=20)
    user.find(marker="loupe-occupant").click()
    assert _champ(user, "recherche-client").value == "ZÉPHYRIN LOUPE"
    await user.should_see(f"resultat-client-{connu}", retries=20)

    user.find(marker="client-sejour").click()
    assert not (_champ(user, "recherche-client").value or "").strip()
    assert _champ(user, "creer-client").enabled is False


async def test_la_vente_propose_le_prix_du_catalogue_et_garde_la_remise(user: User) -> None:
    await _ouvrir_session(user, "vente-produit@hotel-panorama.fr")
    cafe = creer_produit("Café vente", 250)
    the = creer_produit("Thé vente", 300)
    reservation_id = creer_reservation()

    await user.open(f"/reservations/{reservation_id}")
    await user.should_see("Fiche séjour")
    user.find(marker="ajouter-consommation").click()
    await user.should_see("Choisissez un produit")

    select = _champ(user, "produit-consommation")
    prix = _champ(user, "prix-consommation")
    assert {cafe, the} <= set(select.options)
    select.set_value(cafe)
    assert prix.value == 2.5
    select.set_value(the)
    assert prix.value == 3
    select.set_value(cafe)
    prix.set_value(1)
    _champ(user, "quantite-consommation").set_value(2)

    sirop = creer_produit("Sirop vente", 500)
    _champ(user, "onglets-fiche").set_value("consommations")
    for _ in range(40):
        if sirop in select.options:
            break
        await asyncio.sleep(0.05)
    assert sirop in select.options
    assert select.value == cafe
    assert prix.value == 1

    user.find(marker="ajouter-consommation").click()
    await user.should_see("Consommation ajoutée")
    [ligne] = fiche_sejour(reservation_id)["consommations"]
    assert (ligne["libelle"], ligne["quantite"], ligne["prix_unitaire_centimes"]) == ("Café vente", 2, 100)
    assert _champ(user, "produit-consommation").value is None
    assert next(produit.prix_unitaire_centimes for produit in lister_produits() if produit.id == cafe) == 250


async def test_un_produit_desactive_avant_validation_est_refuse(user: User) -> None:
    await _ouvrir_session(user, "vente-retiree@hotel-panorama.fr")
    cafe = creer_produit("Café retiré", 250)
    reservation_id = creer_reservation()

    await user.open(f"/reservations/{reservation_id}")
    await user.should_see("Fiche séjour")
    select = _champ(user, "produit-consommation")
    select.set_value(cafe)
    assert _champ(user, "prix-consommation").value == 2.5
    definir_produit_actif(cafe, False)
    user.find(marker="ajouter-consommation").click()
    await user.should_see("n'est plus en vente")

    assert fiche_sejour(reservation_id)["consommations"] == []
    assert select.value is None
    assert cafe not in select.options


async def test_une_consommation_se_modifie_dans_la_ligne(user: User) -> None:
    await _ouvrir_session(user, "ligne-consommation@hotel-panorama.fr")
    cafe = creer_produit("Café ligne", 250)
    reservation_id = creer_reservation()

    await user.open(f"/reservations/{reservation_id}")
    await user.should_see("Fiche séjour")
    _champ(user, "produit-consommation").set_value(cafe)
    user.find(marker="ajouter-consommation").click()
    await user.should_see("Consommation ajoutée")
    identifiant = fiche_sejour(reservation_id)["consommations"][0]["id"]

    _champ(user, f"quantite-ligne-{identifiant}").set_value(4)
    user.find(marker=f"quantite-ligne-{identifiant}").trigger("blur")
    await user.should_see("Consommation modifiée")
    assert fiche_sejour(reservation_id)["consommations"][0]["quantite"] == 4
    await user.should_see("10,00")

    _champ(user, f"prix-ligne-{identifiant}").set_value(1.5)
    user.find(marker=f"prix-ligne-{identifiant}").trigger("blur")
    ligne = await _ligne_consommation(reservation_id, prix_unitaire_centimes=150)
    assert (ligne["quantite"], ligne["prix_unitaire_centimes"], ligne["montant"]) == (4, 150, 600)

    _champ(user, f"date-ligne-{identifiant}").set_value("05/01/2026")
    ligne = await _ligne_consommation(reservation_id, jour=date(2026, 1, 5))
    moment = ligne["date"]
    jour_affiche = (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).astimezone().date()
    assert jour_affiche == date(2026, 1, 5)
    assert (ligne["libelle"], ligne["quantite"], ligne["prix_unitaire_centimes"]) == ("Café ligne", 4, 150)
    assert next(produit.prix_unitaire_centimes for produit in lister_produits() if produit.id == cafe) == 250

    user.find(marker=f"quantite-ligne-{identifiant}").clear().trigger("blur")
    await user.should_see("La quantité doit être un entier supérieur à 0")
    assert fiche_sejour(reservation_id)["consommations"][0]["quantite"] == 4


async def test_parametres_affiche_la_taxe_et_reprend_l_ancienne_adresse(user: User) -> None:
    with get_session() as session:
        register_user(session, "parametres@hotel-panorama.fr", "Réception", MOT_DE_PASSE)

    await user.open("/login")
    user.find("Email").type("parametres@hotel-panorama.fr")
    user.find("Mot de passe").type(MOT_DE_PASSE)
    user.find("Se connecter").click()
    await user.should_see("Aujourd'hui", retries=30)

    await user.open("/parametres")
    await user.should_see("Paramètres")
    await user.should_see("par adulte et par nuit")

    await user.open("/chambres")
    await user.should_see("Paramètres")
    await user.should_see("par adulte et par nuit")
