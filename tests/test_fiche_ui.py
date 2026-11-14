from datetime import date, timedelta

from nicegui.testing import User

from ma_receptionniste.auth import EmailDejaUtilise, register_user
from ma_receptionniste.consultations import ecran_parametres
from ma_receptionniste.db import get_session
from ma_receptionniste.saisie import ajouter_sejour, creer_chambre, creer_client, creer_reservation, creer_type_chambre

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
