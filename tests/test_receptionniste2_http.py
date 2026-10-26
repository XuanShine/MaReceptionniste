import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from ma_receptionniste2.app import create_app
from ma_receptionniste2.db import moteur

JOUR = date(2026, 10, 12)


@pytest.fixture
def client():
    application = create_app(engine=moteur("sqlite://"), aujourd_hui=lambda: JOUR, secret="test")
    with TestClient(application) as test_client:
        yield test_client


class Bureau:
    def __init__(self, client: TestClient):
        self.client = client
        self.token = ""

    def voir(self, url: str, **kwargs):
        reponse = self.client.get(url, **kwargs)
        self._lire(reponse.text)
        return reponse

    def envoyer(self, url: str, suivre: bool = True, **data):
        reponse = self.client.post(url, data={"csrf": self.token, **data}, follow_redirects=suivre)
        self._lire(reponse.text)
        return reponse

    def _lire(self, html: str) -> None:
        trouve = re.search(r'name="csrf" value="([^"]+)"', html)
        if trouve:
            self.token = trouve.group(1)

    def compte(self, nom: str = "Alice", email: str = "alice@example.com", password: str = "secret"):
        self.voir("/register")
        return self.envoyer("/register", nom=nom, email=email, password=password, confirmation=password)


def _option(html: str, libelle: str) -> str:
    trouve = re.search(rf'<option value="(\d+)"[^>]*>{re.escape(libelle)}</option>', html)
    assert trouve, html
    return trouve.group(1)


def test_les_pages_du_bureau_exigent_un_compte(client: TestClient) -> None:
    reponse = client.get("/", follow_redirects=False)
    assert reponse.status_code == 303
    assert reponse.headers["location"].startswith("/login?redirect_to=")


def test_inscription_connexion_et_deconnexion(client: TestClient) -> None:
    bureau = Bureau(client)
    accueil = bureau.compte()
    assert accueil.status_code == 200
    assert "Aucune chambre" in accueil.text
    assert "Alice" in accueil.text

    bureau.envoyer("/logout")
    refuse = client.get("/chambres", follow_redirects=False)
    assert refuse.status_code == 303
    assert refuse.headers["location"].startswith("/login")

    bureau.voir("/login")
    mauvais = bureau.envoyer("/login", email="alice@example.com", password="mauvais", redirect_to="/chambres")
    assert "Email ou mot de passe incorrect" in mauvais.text

    bureau.voir("/login?redirect_to=https://evil.com")
    piege = client.post(
        "/login",
        data={
            "csrf": bureau.token,
            "email": "alice@example.com",
            "password": "secret",
            "redirect_to": "https://evil.com",
        },
        follow_redirects=False,
    )
    assert piege.status_code == 303
    assert piege.headers["location"] == "/"


def test_inscription_refuse_un_compte_incomplet(client: TestClient) -> None:
    bureau = Bureau(client)
    bureau.voir("/register")
    court = bureau.envoyer("/register", nom="Alice", email="alice@example.com", password="abc", confirmation="abc")
    assert "au moins 4" in court.text
    different = bureau.envoyer(
        "/register", nom="Alice", email="alice@example.com", password="secret", confirmation="autre"
    )
    assert "ne correspondent pas" in different.text
    bureau.compte()
    client.post("/logout", data={"csrf": bureau.token}, follow_redirects=True)
    bureau.voir("/register")
    doublon = bureau.envoyer(
        "/register", nom="Alice", email="Alice@example.com", password="secret", confirmation="secret"
    )
    assert "Un compte existe déjà avec cet email" in doublon.text


def test_jeton_invalide(client: TestClient) -> None:
    bureau = Bureau(client)
    bureau.compte()
    reponse = client.post("/chambres", data={"csrf": "nope", "nom": "101", "position": "1"})
    assert reponse.status_code == 403
    assert "expiré" in reponse.text


def test_le_bureau_cree_chambre_client_sejour_et_note(client: TestClient) -> None:
    bureau = Bureau(client)
    bureau.compte()
    chambres = bureau.envoyer("/chambres", nom="101", position="1")
    assert "101" in chambres.text
    assert "Marquer prête" in chambres.text
    assert "Non prête" in chambres.text
    doublon = bureau.envoyer("/chambres", nom="101", position="2")
    assert "Ce nom de chambre existe déjà" in doublon.text
    identifiant = re.search(r'action="/chambres/(\d+)/etat"', chambres.text)
    assert identifiant
    prete = bureau.envoyer(f"/chambres/{identifiant.group(1)}/etat")
    assert "Prête" in prete.text
    assert "Marquer non prête" in prete.text

    sans_nom = bureau.envoyer("/clients", nom="  ", prenom="", email="", telephone="", adresse="", notes="")
    assert "Le nom est obligatoire" in sans_nom.text
    clients = bureau.envoyer(
        "/clients",
        nom="<b>Dupont</b>",
        prenom="Alice",
        email="dupont@example.com",
        telephone="0600000000",
        adresse="1 rue du Port",
        notes="Arrivée tardive",
    )
    assert "&lt;b&gt;Dupont&lt;/b&gt;" in clients.text
    assert "<b>Dupont</b>" not in clients.text
    assert "Arrivée tardive" in clients.text

    page = bureau.voir("/reservations")
    fiche = bureau.envoyer("/reservations", client_id=_option(page.text, "Alice &lt;b&gt;Dupont&lt;/b&gt;"))
    assert "Aucun séjour" in fiche.text
    chambre = _option(fiche.text, "101")
    sejour = bureau.envoyer(
        _action(fiche.text, "/sejours"),
        chambre_id=chambre,
        nom_client="",
        date_debut="2026-10-12",
        date_fin="2026-10-14",
    )
    assert "12/10/2026" in sejour.text
    assert "14/10/2026" in sejour.text
    occupe = bureau.envoyer(
        _action(sejour.text, "/sejours"),
        chambre_id=chambre,
        nom_client="Martin",
        date_debut="2026-10-13",
        date_fin="2026-10-15",
    )
    assert "déjà occupée" in occupe.text
    voisin = bureau.envoyer(
        _action(occupe.text, "/sejours"),
        chambre_id=chambre,
        nom_client="",
        date_debut="2026-10-14",
        date_fin="2026-10-16",
    )
    assert voisin.text.count("14/10/2026") >= 2

    note = bureau.envoyer(_action(voisin.text, "/notes"), description="Lit bébé")
    assert "Lit bébé" in note.text
    assert "Alice" in note.text
    vide = bureau.envoyer(_action(note.text, "/notes"), description="   ")
    assert "La note est vide" in vide.text

    planning = bureau.voir("/?debut=2026-10-12")
    assert "12 au 18 oct. 2026" in planning.text
    assert "Alice &lt;b&gt;Dupont&lt;/b&gt;" in planning.text
    assert "<b>Dupont</b>" not in planning.text
    assert 'style="grid-column: span 2"' in planning.text
    autre_semaine = bureau.voir("/?debut=2026-10-05")
    assert "5 au 11 oct. 2026" in autre_semaine.text


def test_chevauchement_htmx_reste_sur_la_fiche(client: TestClient) -> None:
    bureau = Bureau(client)
    bureau.compte()
    bureau.envoyer("/chambres", nom="101", position="1")
    bureau.envoyer("/clients", nom="Dupont", prenom="Alice", email="", telephone="", adresse="", notes="")
    page = bureau.voir("/reservations")
    fiche = bureau.envoyer("/reservations", client_id=_option(page.text, "Alice Dupont"))
    url = _action(fiche.text, "/sejours")
    chambre = _option(fiche.text, "101")
    bureau.envoyer(url, chambre_id=chambre, nom_client="", date_debut="2026-10-12", date_fin="2026-10-14")
    fragment = client.post(
        url,
        data={
            "csrf": bureau.token,
            "chambre_id": chambre,
            "nom_client": "",
            "date_debut": "2026-10-13",
            "date_fin": "2026-10-15",
        },
        headers={"HX-Request": "true"},
    )
    assert fragment.status_code == 200
    assert "<html" not in fragment.text.lower()
    assert "déjà occupée" in fragment.text
    assert "12/10/2026" in fragment.text


def test_annulation_libere_la_chambre_sur_le_planning(client: TestClient) -> None:
    bureau = Bureau(client)
    bureau.compte()
    bureau.envoyer("/chambres", nom="101", position="1")
    bureau.envoyer("/clients", nom="Dupont", prenom="Alice", email="", telephone="", adresse="", notes="")
    bureau.envoyer("/clients", nom="Martin", prenom="Bob", email="", telephone="", adresse="", notes="")
    page = bureau.voir("/reservations")
    alice = bureau.envoyer("/reservations", client_id=_option(page.text, "Alice Dupont"))
    chambre = _option(alice.text, "101")
    bureau.envoyer(
        _action(alice.text, "/sejours"),
        chambre_id=chambre,
        nom_client="Ne pas afficher",
        date_debut="2026-10-12",
        date_fin="2026-10-14",
    )
    bureau.envoyer(_action(alice.text, "/annuler"))
    page = bureau.voir("/reservations")
    bob = bureau.envoyer("/reservations", client_id=_option(page.text, "Bob Martin"))
    pose = bureau.envoyer(
        _action(bob.text, "/sejours"),
        chambre_id=_option(bob.text, "101"),
        nom_client="",
        date_debut="2026-10-12",
        date_fin="2026-10-14",
    )
    assert "déjà occupée" not in pose.text
    planning = bureau.voir("/?debut=2026-10-12")
    assert "Bob Martin" in planning.text
    assert "Ne pas afficher" not in planning.text
    assert "Alice Dupont" not in planning.text


def _action(html: str, suffixe: str) -> str:
    trouve = re.search(rf'action="(/reservations/\d+{suffixe})"', html)
    assert trouve, html
    return trouve.group(1)
