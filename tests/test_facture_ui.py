import asyncio
from datetime import date, timedelta

from nicegui.testing import User

from ma_receptionniste.auth import EmailDejaUtilise, register_user
from ma_receptionniste.consultations import fiche_sejour
from ma_receptionniste.db import get_session
from ma_receptionniste.facturation import (
    IdentiteFacturation,
    enregistrer_identite,
    identite_vide,
    lire_identite,
    lister_factures,
)
from ma_receptionniste.models import FormeJuridique, RegimeTVA
from ma_receptionniste.saisie import (
    ajouter_sejour,
    creer_chambre,
    creer_client,
    creer_reservation,
    creer_type_chambre,
    enregistrer_fiche,
)

MOT_DE_PASSE = "panorama-facture"


def _champ(user: User, marker: str):
    return next(iter(user.find(marker=marker).elements))


def _identite() -> None:
    enregistrer_identite(
        IdentiteFacturation(
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
    )


def _sejour(nom: str, email: str) -> int:
    with get_session() as session:
        try:
            register_user(session, email, "Réception", MOT_DE_PASSE)
        except EmailDejaUtilise:
            pass
    client_id = creer_client(nom, email="client@hotel.fr", adresse="1 rue du Port, 29200 Brest")
    reservation_id = creer_reservation(client_id)
    hier = date.today() - timedelta(days=1)
    type_id = creer_type_chambre(f"Single {nom}")
    chambre_id = creer_chambre(f"12-{reservation_id}", 1, type_chambre_id=type_id)
    ajouter_sejour(reservation_id, chambre_id, hier, hier + timedelta(days=2), prix_nuit_centimes=6882)
    return reservation_id


async def _attendre_apercu(user: User) -> None:
    for _ in range(120):
        dialogues = user.find(marker="dialogue-apercu").elements
        if dialogues and next(iter(dialogues)).value and user.find(marker="pdf-facture").elements:
            return
        await asyncio.sleep(0.1)
    raise AssertionError("l'aperçu PDF ne s'est pas ouvert")


async def _ouvrir(user: User, email: str, reservation_id: int) -> None:
    await user.open("/login")
    user.find("Email").type(email)
    user.find("Mot de passe").type(MOT_DE_PASSE)
    user.find("Se connecter").click()
    await user.should_see("Aujourd'hui", retries=30)
    await user.open(f"/reservations/{reservation_id}")
    await user.should_see("Facturer")


async def test_apercu_puis_enregistrement(user: User) -> None:
    _identite()
    reservation_id = _sejour("MARTIN FACTURE", "facture-ui@hotel-panorama.fr")
    enregistrer_fiche(reservation_id, None, {"nom_occupant": "MARTIN OCCUPANT"})
    await _ouvrir(user, "facture-ui@hotel-panorama.fr", reservation_id)

    user.find("Facturer").click()
    await user.should_see("Aperçu", retries=20)
    await user.should_not_see("Nom de la facture")
    await user.should_not_see("Aperçu — facture non émise")
    assert _champ(user, "nom-facture").value == "MARTIN OCCUPANT"
    _champ(user, "nom-facture").set_value("Facturation Client")
    user.find(marker="retour-nom").click()
    assert fiche_sejour(reservation_id)["reservation"]["numero_facture"] is None
    assert lister_factures(reservation_id) == []

    user.find("Facturer").click()
    await user.should_see("Aperçu", retries=20)
    assert _champ(user, "nom-facture").value == "MARTIN OCCUPANT"
    _champ(user, "nom-facture").set_value("Facturation Client")
    user.find(marker="apercu-facture").click()
    await _attendre_apercu(user)
    assert fiche_sejour(reservation_id)["reservation"]["numero_facture"] is None
    assert fiche_sejour(reservation_id)["reservation"]["facturation"] in (None, "")

    user.find(marker="retour-apercu").click()
    await user.should_see("Aperçu", retries=10)
    assert _champ(user, "nom-facture").value == "Facturation Client"

    user.find(marker="apercu-facture").click()
    await _attendre_apercu(user)
    user.find(marker="enregistrer-facture").click()
    await user.should_see("L'envoi par email n'est pas configuré", retries=120)
    await user.should_see("Imprimer")
    await user.should_see("Annule et remplace")
    assert user.find(marker="pdf-facture").elements

    fiche = fiche_sejour(reservation_id)
    numero = fiche["reservation"]["numero_facture"]
    assert numero is not None
    assert fiche["reservation"]["facturation"] == "Facturation Client"
    assert len(lister_factures(reservation_id)) == 1
    await user.should_see(f"Facture n° {numero}")

    user.find("Fermer").click()
    user.find(marker="numero-facture").click()
    await user.should_see(f"Facture n° {numero}", retries=20)
    await user.should_see("Annule et remplace")
    user.find(marker="annule-remplace").click()
    await user.should_see("Aperçu", retries=20)
    assert _champ(user, "nom-facture").value == "Facturation Client"
    user.find(marker="retour-nom").click()
    assert len(lister_factures(reservation_id)) == 1


async def test_apercu_bloque_sans_mentions(user: User) -> None:
    enregistrer_identite(identite_vide())
    reservation_id = _sejour("SANS MENTION", "facture-mentions@hotel-panorama.fr")
    await _ouvrir(user, "facture-mentions@hotel-panorama.fr", reservation_id)
    user.find("Facturer").click()
    await user.should_see("Aperçu", retries=20)
    user.find(marker="apercu-facture").click()
    await user.should_see("dénomination sociale", retries=20)
    assert fiche_sejour(reservation_id)["reservation"]["numero_facture"] is None
    assert lister_factures(reservation_id) == []


async def test_parametres_enregistrent_l_identite_incomplete(user: User) -> None:
    email = "identite-ui@hotel-panorama.fr"
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
    await user.open("/parametres")
    await user.should_see("Informations de facturation de l'hôtel", retries=20)
    user.find(marker="enregistrer-identite").click()
    await user.should_see("Informations de facturation enregistrées", retries=20)
    _champ(user, "denomination-hotel").set_value("Panorama SAS")
    user.find(marker="enregistrer-identite").click()
    for _ in range(40):
        if lire_identite().denomination == "Panorama SAS":
            break
        await asyncio.sleep(0.05)
    assert lire_identite().denomination == "Panorama SAS"
    await user.open("/parametres")
    await user.should_see("Informations de facturation de l'hôtel", retries=20)
    assert _champ(user, "denomination-hotel").value == "Panorama SAS"
