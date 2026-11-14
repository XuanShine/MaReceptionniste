from nicegui.testing import User

from ma_receptionniste.auth import EmailDejaUtilise, register_user
from ma_receptionniste.db import get_session

EMAIL = "dashboard@hotel-panorama.fr"
MOT_DE_PASSE = "panorama-dashboard"


def _compte() -> None:
    with get_session() as session:
        try:
            register_user(session, EMAIL, "Réception", MOT_DE_PASSE)
        except EmailDejaUtilise:
            pass


async def test_le_tableau_de_bord_porte_les_compteurs_et_le_planning_la_grille(user: User) -> None:
    _compte()
    await user.open("/login")
    user.find("Email").type(EMAIL)
    user.find("Mot de passe").type(MOT_DE_PASSE)
    user.find("Se connecter").click()
    await user.should_see("Aujourd'hui", retries=30)

    await user.open("/dashboard")
    await user.should_see("Arrivées")
    await user.should_see("Départs")
    await user.should_see("En maison")
    await user.should_see("Chambres non prêtes")

    await user.open("/")
    await user.should_see("Aujourd'hui")
    await user.should_not_see("Chambres non prêtes")
