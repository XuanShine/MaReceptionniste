from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from ma_receptionniste.auth import EmailDejaUtilise, register_user
from ma_receptionniste.db import get_session
from ma_receptionniste.facturation import format_euros
from ma_receptionniste.saisie import (
    ajouter_sejour,
    creer_chambre,
    creer_client,
    creer_reservation,
    creer_type_chambre,
)
from ma_receptionniste.web.app import create_app

EMAIL = "interface@hotel-panorama.fr"
MOT_DE_PASSE = "panorama-interface"


@pytest.fixture
def client(base):
    with TestClient(create_app()) as navigateur:
        yield navigateur


def _compte(email: str = EMAIL, nom: str = "Réception", mot_de_passe: str = MOT_DE_PASSE) -> None:
    with get_session() as session:
        try:
            register_user(session, email, nom, mot_de_passe)
        except EmailDejaUtilise:
            pass


def _connecter(navigateur: TestClient, email: str = EMAIL, mot_de_passe: str = MOT_DE_PASSE) -> None:
    _compte(email, mot_de_passe=mot_de_passe)
    reponse = navigateur.post(
        "/login",
        data={"email": email, "password": mot_de_passe, "redirect_to": "/"},
        follow_redirects=False,
    )
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/"


def _sejour() -> int:
    _compte()
    reservation_id = creer_reservation(creer_client("Bénédicte LE CLOEREC", pays="France"))
    hier = date.today() - timedelta(days=1)
    chambre_id = creer_chambre(f"406-{reservation_id}", 1, type_chambre_id=creer_type_chambre("Single BB"))
    ajouter_sejour(reservation_id, chambre_id, hier, hier + timedelta(days=2), prix_nuit_centimes=6882)
    return reservation_id


def test_une_page_privee_renvoie_vers_la_connexion(client: TestClient) -> None:
    reponse = client.get("/dashboard", follow_redirects=False)
    assert reponse.status_code == 303
    assert reponse.headers["location"].startswith("/login?redirect_to=%2Fdashboard")


def test_la_connexion_ouvre_le_planning_et_le_tableau_de_bord(client: TestClient) -> None:
    _connecter(client, "dashboard@hotel-panorama.fr", "panorama-dashboard")
    accueil = client.get("/")
    assert "Aujourd'hui" in accueil.text
    assert "Chambres non prêtes" not in accueil.text
    tableau = client.get("/dashboard")
    for libelle in ("Arrivées", "Départs", "En maison", "Chambres non prêtes"):
        assert libelle in tableau.text


def test_un_mauvais_mot_de_passe_reste_sur_la_connexion(client: TestClient) -> None:
    _compte("dashboard@hotel-panorama.fr", mot_de_passe="panorama-dashboard")
    reponse = client.post(
        "/login",
        data={"email": "dashboard@hotel-panorama.fr", "password": "non", "redirect_to": "https://evil.com"},
    )
    assert "Email ou mot de passe incorrect" in reponse.text
    assert reponse.url.path == "/login"


def test_la_fiche_montre_la_ligne_le_total_et_le_brouillon(client: TestClient) -> None:
    reservation_id = _sejour()
    _connecter(client, EMAIL, MOT_DE_PASSE)
    fiche = client.get(f"/reservations/{reservation_id}")
    assert "Bénédicte LE CLOEREC" in fiche.text
    assert "Réservations (1)" in fiche.text
    assert "Facturer" in fiche.text
    assert format_euros(14164) in fiche.text

    brouillon = client.get(f"/reservations/{reservation_id}/lignes/nouvelle", headers={"HX-Request": "true"})
    assert "Enregistrer" in brouillon.text
    assert "<table>" in brouillon.text
    assert "Ajouter une nouvelle ligne" not in brouillon.text
    assert "Nouvelle ligne de séjour" not in brouillon.text


def test_enregistrer_une_ligne_la_montre_dans_le_tableau(client: TestClient) -> None:
    reservation_id = _sejour()
    _connecter(client)
    debut = date.today() + timedelta(days=10)
    chambre_id = creer_chambre(f"407-{reservation_id}", 2, type_chambre_id=creer_type_chambre("Double"))
    reponse = client.post(
        f"/reservations/{reservation_id}/lignes",
        data={
            "chambre_id": chambre_id,
            "date_debut": debut.isoformat(),
            "date_fin": (debut + timedelta(days=2)).isoformat(),
            "adultes": "1",
            "enfants": "0",
            "prix": "50",
            "remise": "0",
        },
        follow_redirects=True,
    )
    assert "407-" in reponse.text
    assert "Réservations (2)" in reponse.text


def test_une_adresse_externe_revient_a_l_accueil(client: TestClient) -> None:
    _compte("redirect@hotel-panorama.fr", mot_de_passe="panorama")
    reponse = client.post(
        "/login",
        data={"email": "redirect@hotel-panorama.fr", "password": "panorama", "redirect_to": "https://evil.com"},
        follow_redirects=False,
    )
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/"


def test_l_inscription_refuse_un_mot_de_passe_trop_court(client: TestClient) -> None:
    reponse = client.post(
        "/register",
        data={"nom": "Ada", "email": "ada@hotel-panorama.fr", "password": "abc", "confirmation": "abc"},
    )
    assert "Le mot de passe doit faire au moins 4 caractères" in reponse.text


def test_ajouter_un_client_et_une_chambre(client: TestClient) -> None:
    _connecter(client)
    clients = client.post("/clients", data={"nom": "Léa MARTIN", "pays": "France"}, follow_redirects=True)
    assert "Client ajouté" in clients.text
    assert "Léa MARTIN" in clients.text
    assert "1 client" in clients.text
    vide = client.post("/clients", data={"nom": "  "}, follow_redirects=True)
    assert "Le nom est obligatoire" in vide.text

    chambres = client.post(
        "/chambres", data={"nom": "12", "type_chambre": "Double", "position": "3"}, follow_redirects=True
    )
    assert "Chambre ajoutée" in chambres.text
    assert "Marquer prête" in chambres.text
    client.post("/chambres/1/etat", headers={"HX-Request": "true", "HX-Target": "liste-chambres"})
    liste = client.get("/chambres")
    assert liste.url.path == "/parametres"
    assert "Marquer non prête" in liste.text


def test_facturer_emet_un_numero(client: TestClient) -> None:
    reservation_id = _sejour()
    _connecter(client)
    reponse = client.post(f"/reservations/{reservation_id}/facturer", follow_redirects=True)
    assert "Facture n° 1 émise" in reponse.text
    assert "1" in reponse.text


def test_confirmer_ecrit_le_journal_sans_quitter_la_fiche(client: TestClient) -> None:
    reservation_id = _sejour()
    _connecter(client)
    reponse = client.post(
        f"/reservations/{reservation_id}",
        data={
            "nom": "Bénédicte LE CLOEREC",
            "pays": "France",
            "type_voiture": "Tesla",
            "ensuite": "rester",
        },
        headers={"HX-Request": "true"},
    )
    assert "Fiche enregistrée" in reponse.text
    assert "Modifications (2)" in reponse.text
    assert "Type voiture" in reponse.text
    assert "LE CLOEREC" in reponse.text


def _valeur_option(html: str, libelle: str) -> str:
    avant = html.split(f">{libelle}</option>", 1)[0]
    return avant.rsplit('value="', 1)[1].split('"', 1)[0]


def test_les_parametres_relient_une_chambre_a_un_type_et_une_occupation(client: TestClient) -> None:
    _connecter(client)
    types = client.post("/types-chambres", data={"libelle": "Double"}, follow_redirects=True)
    assert "Type ajouté" in types.text
    occupations = client.post(
        "/occupations-chambres",
        data={"nombre_personnes": "2", "type_lits": "Lit double"},
        follow_redirects=True,
    )
    assert "Occupation ajoutée" in occupations.text
    page = client.post(
        "/chambres",
        data={
            "nom": "12",
            "position": "1",
            "type_chambre_id": _valeur_option(occupations.text, "Double"),
            "occupation_chambre_id": _valeur_option(occupations.text, "2 · Lit double"),
        },
        follow_redirects=True,
    )
    assert "Chambre ajoutée" in page.text
    assert page.url.path == "/parametres"
    assert "Double" in page.text
    assert "Lit double" in page.text
    assert 'href="/chambres"' not in page.text
    refus = client.post(
        f"/types-chambres/{_valeur_option(page.text, 'Double')}/supprimer",
        follow_redirects=True,
    )
    assert "Ce type est utilisé par une chambre" in refus.text
    assert "Double" in refus.text


def test_le_menu_ouvre_les_parametres(client: TestClient) -> None:
    _connecter(client)
    accueil = client.get("/")
    assert 'href="/parametres"' in accueil.text
    assert "bg-primary-soft" not in accueil.text.split('href="/parametres"', 1)[1][:160]
    page = client.get("/parametres")
    assert page.status_code == 200
    assert "<h1" in page.text and "Paramètres" in page.text
    assert "Hôtel Panorama" in page.text
    assert format_euros(200) in page.text
    assert "Nouvelle chambre" in page.text
    assert "bg-primary-soft" in page.text.split('href="/parametres"', 1)[1][:160]
    assert 'href="/chambres"' not in accueil.text


def test_la_deconnexion_referme_les_pages(client: TestClient) -> None:
    _connecter(client)
    client.post("/logout", follow_redirects=False)
    reponse = client.get("/", follow_redirects=False)
    assert reponse.status_code == 303
    assert reponse.headers["location"].startswith("/login")
