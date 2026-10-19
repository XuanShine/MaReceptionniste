from datetime import date, timedelta

from nicegui.testing import User

from ma_receptionniste.auth import register_user
from ma_receptionniste.db import get_session
from ma_receptionniste.saisie import ajouter_sejour, creer_chambre, creer_client, creer_reservation

EMAIL = "fiche@hotel-panorama.fr"
MOT_DE_PASSE = "panorama-fiche"


def _reservation_de_la_capture() -> int:
    with get_session() as session:
        register_user(session, EMAIL, "Réception", MOT_DE_PASSE)
    reservation_id = creer_reservation(creer_client("LE CLOEREC", "Bénédicte", pays="France"))
    hier = date.today() - timedelta(days=1)
    chambre_id = creer_chambre("406", 1, "Single BB")
    ajouter_sejour(reservation_id, chambre_id, hier, hier + timedelta(days=2), prix_nuit_centimes=6882)
    return reservation_id


async def test_la_fiche_montre_la_ligne_les_actions_et_le_total(user: User) -> None:
    reservation_id = _reservation_de_la_capture()

    await user.open("/login")
    user.find("Email").type(EMAIL)
    user.find("Mot de passe").type(MOT_DE_PASSE)
    user.find("Se connecter").click()
    await user.should_see("Arrivées")

    await user.open(f"/reservations/{reservation_id}")
    await user.should_see("Bénédicte LE CLOEREC")
    await user.should_see("Réservations (1)")
    await user.should_see("Facturer")
    # 2 nuits à 68,82 € et 2 nuits de taxe à 2,00 € pour un adulte.
    await user.should_see("141,64\u00a0€")
