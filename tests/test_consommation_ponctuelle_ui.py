import asyncio
from datetime import date, timedelta

from nicegui import ui
from nicegui.testing import User

from ma_receptionniste.auth import EmailDejaUtilise, register_user
from ma_receptionniste.consommation_ponctuelle import cle_chambre, ecrire, lire
from ma_receptionniste.consultations import ecran_parametres, fiche_sejour
from ma_receptionniste.db import get_session
from ma_receptionniste.models import Reservation
from ma_receptionniste.saisie import (
    ajouter_sejour,
    creer_chambre,
    creer_client,
    creer_produit,
    creer_reservation,
    creer_type_chambre,
    definir_produit_actif,
)

EMAIL = "ponctuelle-ui@hotel-panorama.fr"
MOT_DE_PASSE = "panorama-fiche"
PRODUIT = "Petit-déjeuner fiche"
ARRIVEE = date(2026, 11, 10)
DEPART = date(2026, 11, 12)
JOUR_COCHE = date(2026, 11, 12)


def _type_single_bb() -> int:
    connus = {ligne["libelle"]: ligne["id"] for ligne in ecran_parametres()["types"]}
    if "Single BB" in connus:
        return connus["Single BB"]
    return creer_type_chambre("Single BB")


def _poser(reservation_id: int, brut: str) -> None:
    with get_session() as session:
        reservation = session.get(Reservation, reservation_id)
        assert reservation is not None
        reservation.notes_internes = brut
        session.add(reservation)
        session.commit()


def _champ(user: User, marker: str):
    return next(iter(user.find(marker=marker).elements))


def _alerte(user: User):
    return _champ(user, "onglet-ponctuelle").props.get("alert")


async def _ouvrir(user: User, email: str, reservation_id: int) -> None:
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
    await user.open(f"/reservations/{reservation_id}")
    await user.should_see("Consommation ponctuelle")


async def _attendre_historique(reservation_id: int, description: str) -> None:
    for _ in range(40):
        if description in [note["description"] for note in fiche_sejour(reservation_id)["historique"]]:
            return
        await asyncio.sleep(0.05)
    raise AssertionError([note["description"] for note in fiche_sejour(reservation_id)["historique"]])


def _sejour(debut: date = ARRIVEE, fin: date = DEPART) -> tuple[int, int, str]:
    reservation_id = creer_reservation(creer_client("LE CLOEREC", pays="France"))
    chambre = f"12-{reservation_id}"
    chambre_id = creer_chambre(chambre, 1, type_chambre_id=_type_single_bb())
    sejour_id = ajouter_sejour(reservation_id, chambre_id, debut, fin, prix_nuit_centimes=5000)
    return reservation_id, sejour_id, chambre


async def test_l_onglet_coche_la_note_et_le_point_rouge_suit_les_dates(user: User) -> None:
    petit_dejeuner = creer_produit(PRODUIT, 900, ponctuel=True)
    cafe = creer_produit("Café fiche", 200)
    retire = creer_produit("Buffet fiche", 1200, ponctuel=True)
    definir_produit_actif(retire, False)
    reservation_id, sejour_id, chambre = _sejour()
    _poser(
        reservation_id,
        ecrire({"Consommation": {cle_chambre(chambre): {"Ancien buffet": {date(2026, 11, 11): 1}}}}),
    )

    await _ouvrir(user, EMAIL, reservation_id)
    assert _alerte(user) is None
    options = _champ(user, "produit-ponctuel").options
    assert options[petit_dejeuner] == PRODUIT
    assert cafe not in options
    assert retire not in options
    gris = _champ(user, "gris-ponctuel|Ancien buffet")
    assert "text-slate-400" in gris.classes
    await user.should_see("Hors catalogue")
    assert _champ(user, "tableau-ponctuel").tag == "table"
    assert _champ(user, "entete-ponctuel|produit").tag == "th"
    assert _champ(user, "entete-ponctuel|chambre").tag == "th"
    assert _champ(user, "entete-ponctuel|nombre").tag == "th"
    case_ancien = _champ(user, f"case-ponctuelle|{chambre}|Ancien buffet|2026-11-11")
    assert case_ancien.value is True
    assert any(parent.tag == "td" for parent in case_ancien.ancestors())

    _champ(user, "produit-ponctuel").set_value(petit_dejeuner)
    _champ(user, "chambre-ponctuelle").set_value(chambre)
    _champ(user, "nombre-ponctuel").set_value(2)
    user.find(marker="ajouter-ponctuelle").click()
    case = f"case-ponctuelle|{chambre}|{PRODUIT}|{JOUR_COCHE.isoformat()}"
    await user.should_see(marker=case, retries=20)
    assert _champ(user, case).value is False

    user.find(marker=case).click()
    await _attendre_historique(reservation_id, f"{PRODUIT} · Chambre {chambre} · 12/11 : 2")
    await user.should_see(marker=f"total-ponctuel|{chambre}|{PRODUIT}", retries=20)
    assert _champ(user, f"total-ponctuel|{chambre}|{PRODUIT}").text == "2"
    note = lire(fiche_sejour(reservation_id)["reservation"]["notes_internes"])
    assert note["Consommation"][cle_chambre(chambre)][PRODUIT][JOUR_COCHE] == 2
    assert "Ancien buffet" in note["Consommation"][cle_chambre(chambre)]
    assert fiche_sejour(reservation_id)["consommations"] == []
    assert _alerte(user) is None

    user.find(marker=f"ligne-sejour-{sejour_id}").click()
    await user.should_see("Ligne de séjour", retries=20)
    _champ(user, "depart-ligne").set_value("11/11/2026")
    user.find(marker="enregistrer-ligne").click()
    await user.should_see("Ligne modifiée", retries=20)
    for _ in range(40):
        if _alerte(user) == "negative":
            break
        await asyncio.sleep(0.05)
    assert _alerte(user) == "negative"
    await user.should_see("hors du séjour")
    await user.should_see("12/11/2026")
    note = lire(fiche_sejour(reservation_id)["reservation"]["notes_internes"])
    assert JOUR_COCHE in note["Consommation"][cle_chambre(chambre)][PRODUIT]

    user.find(marker=case).click()
    await _attendre_historique(reservation_id, f"{PRODUIT} · Chambre {chambre} · 12/11 : retiré")
    for _ in range(40):
        if _alerte(user) is None:
            break
        await asyncio.sleep(0.05)
    assert _alerte(user) is None
    note = lire(fiche_sejour(reservation_id)["reservation"]["notes_internes"])
    assert PRODUIT not in note["Consommation"][cle_chambre(chambre)]
    assert note["Consommation"][cle_chambre(chambre)]["Ancien buffet"][date(2026, 11, 11)] == 1
    assert fiche_sejour(reservation_id)["consommations"] == []


async def test_la_colonne_du_jour_est_surlignee(user: User) -> None:
    aujourd_hui = date.today()
    reservation_id, _, chambre = _sejour(aujourd_hui - timedelta(days=1), aujourd_hui + timedelta(days=1))
    _poser(
        reservation_id,
        ecrire({"Consommation": {cle_chambre(chambre): {"Ancien buffet": {aujourd_hui: 1}}}}),
    )

    await _ouvrir(user, "ponctuelle-jour@hotel-panorama.fr", reservation_id)
    assert "bg-primary-pale" in _champ(user, f"entete-ponctuel|{aujourd_hui.isoformat()}").classes
    veille = aujourd_hui - timedelta(days=1)
    assert "bg-primary-pale" not in _champ(user, f"entete-ponctuel|{veille.isoformat()}").classes
    case = _champ(user, f"case-ponctuelle|{chambre}|Ancien buffet|{aujourd_hui.isoformat()}")
    cellule = next(parent for parent in case.ancestors() if parent.tag == "td")
    assert "bg-primary-pale" in cellule.classes


async def test_une_note_illisible_laisse_l_onglet_en_lecture_seule(user: User) -> None:
    reservation_id, _, _ = _sejour()
    _poser(reservation_id, "[")
    avant = [note["description"] for note in fiche_sejour(reservation_id)["historique"]]

    await _ouvrir(user, "ponctuelle-illisible@hotel-panorama.fr", reservation_id)
    await user.should_see("La note interne est illisible. Aucune modification ne sera enregistrée.")
    await user.should_not_see(marker="ajouter-ponctuelle")
    assert _alerte(user) is None
    zone = _champ(user, "note-illisible")
    saisie = next(element for element in zone.descendants() if isinstance(element, ui.textarea))
    assert saisie.value == "["
    assert "readonly" in saisie.props

    fiche = fiche_sejour(reservation_id)
    assert fiche["reservation"]["notes_internes"] == "["
    assert [note["description"] for note in fiche["historique"]] == avant
    assert fiche["consommations"] == []
