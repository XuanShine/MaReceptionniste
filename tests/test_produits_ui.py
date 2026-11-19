from nicegui import ui
from nicegui.testing import User

from ma_receptionniste.auth import EmailDejaUtilise, register_user
from ma_receptionniste.consultations import lister_produits
from ma_receptionniste.db import get_session
from ma_receptionniste.saisie import creer_produit

EMAIL = "produits-ui@hotel-panorama.fr"
MOT_DE_PASSE = "panorama-produits"


def _champ(user: User, marker: str):
    return next(iter(user.find(marker=marker).elements))


async def _ouvrir(user: User) -> None:
    with get_session() as session:
        try:
            register_user(session, EMAIL, "Réception", MOT_DE_PASSE)
        except EmailDejaUtilise:
            pass
    await user.open("/login")
    user.find("Email").type(EMAIL)
    user.find("Mot de passe").type(MOT_DE_PASSE)
    user.find("Se connecter").click()
    await user.should_see("Aujourd'hui", retries=30)


async def test_le_menu_ouvre_la_page_produits(user: User) -> None:
    await _ouvrir(user)
    assert any(lien.props.get("href") == "/produits" for lien in user.find(ui.link).elements)
    await user.open("/produits")
    await user.should_see("Nouveau produit", retries=20)
    await user.should_see("Rechercher un produit…")


async def test_creer_rechercher_modifier_et_desactiver_un_produit(user: User) -> None:
    await _ouvrir(user)
    await user.open("/produits")
    user.find(marker="creer-produit").click()
    await user.should_see("Le nom est obligatoire")

    _champ(user, "nom-produit").set_value("Pomme page")
    _champ(user, "prix-produit").set_value(2.5)
    _champ(user, "tva-produit").set_value(55)
    user.find(marker="creer-produit").click()
    await user.should_see("Produit ajouté")
    pomme = next(produit.id for produit in lister_produits() if produit.nom == "Pomme page")
    assert next(produit for produit in lister_produits() if produit.id == pomme).taux_tva_pour_mille == 55
    await user.should_see(f"nom-produit-{pomme}")
    await user.should_see("5,5")
    await user.should_see("2,50")

    _champ(user, "nom-produit").set_value("Pomme page")
    _champ(user, "prix-produit").set_value(1)
    user.find(marker="creer-produit").click()
    await user.should_see("Ce produit existe déjà")

    poire = creer_produit("Poire page", 180)
    await user.open("/produits")
    _champ(user, "recherche-produit").set_value("poire")
    await user.should_see(f"nom-produit-{poire}")
    await user.should_not_see(f"nom-produit-{pomme}")

    _champ(user, "recherche-produit").set_value("")
    await user.should_see(f"nom-produit-{pomme}")
    user.find(marker=f"modifier-produit-{pomme}").click()
    assert _champ(user, "nom-edition").value == "Pomme page"
    assert _champ(user, "tva-edition").value == 55
    _champ(user, "nom-edition").set_value("Compote page")
    _champ(user, "prix-edition").set_value(4)
    _champ(user, "tva-edition").set_value(200)
    user.find(marker="enregistrer-produit").click()
    await user.should_see("Produit modifié")
    await user.should_see("Compote page")
    await user.should_see("20")
    modifie = next(produit for produit in lister_produits() if produit.id == pomme)
    assert (modifie.prix_unitaire_centimes, modifie.taux_tva_pour_mille) == (400, 200)

    with user.scope(marker=f"ligne-produit-{pomme}"):
        user.find("Désactiver").click()
    await user.should_see("Produit désactivé")
    with user.scope(marker=f"ligne-produit-{pomme}"):
        await user.should_see("Inactif")
        await user.should_see("Réactiver")
    assert next(produit for produit in lister_produits() if produit.id == pomme).actif is False

    with user.scope(marker=f"ligne-produit-{pomme}"):
        user.find("Réactiver").click()
    await user.should_see("Produit réactivé")
    assert next(produit for produit in lister_produits() if produit.id == pomme).actif is True


async def test_la_case_ponctuel_est_enregistree(user: User) -> None:
    await _ouvrir(user)
    await user.open("/produits")
    _champ(user, "nom-produit").set_value("Brunch page")
    _champ(user, "prix-produit").set_value(9)
    _champ(user, "ponctuel-produit").set_value(True)
    user.find(marker="creer-produit").click()
    await user.should_see("Produit ajouté")

    brunch = next(produit for produit in lister_produits() if produit.nom == "Brunch page")
    assert brunch.ponctuel is True
    await user.should_see(f"ponctuel-etat-{brunch.id}")
    assert _champ(user, f"ponctuel-etat-{brunch.id}").text == "Oui"

    user.find(marker=f"modifier-produit-{brunch.id}").click()
    assert _champ(user, "ponctuel-edition").value is True
    _champ(user, "ponctuel-edition").set_value(False)
    user.find(marker="enregistrer-produit").click()
    await user.should_see("Produit modifié")
    assert next(produit for produit in lister_produits() if produit.id == brunch.id).ponctuel is False
    assert _champ(user, f"ponctuel-etat-{brunch.id}").text == "—"
