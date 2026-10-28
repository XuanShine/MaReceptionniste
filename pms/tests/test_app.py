import re
from html import unescape
from pathlib import Path

from hotel_pms.auth import verifier_mot_de_passe
from hotel_pms.models import Sejour, User
from hotel_pms.seed import JOURNAL_MONNIER, NOTES_MONNIER
from sqlalchemy import inspect
from sqlmodel import Session, select
from tests.conftest import id_monnier, jeton, login

MENU = [
    "Dashboard",
    "Planning",
    "Séjours",
    "Détails Séjour",
    "Produits",
    "Chambres",
    "Clients",
    "Paramètres",
]


def test_tables_sqlite_et_mot_de_passe_hashe(client):
    assert Path(client.app.state.db_path).is_file()
    tables = set(inspect(client.app.state.engine).get_table_names())
    for nom in (
        "user",
        "client",
        "chambre",
        "produit",
        "sejour",
        "ligne_reservation",
        "reglement",
        "modification_sejour",
    ):
        assert nom in tables
    with Session(client.app.state.engine) as session:
        user = session.exec(select(User)).one()
        assert user.password_hash != "reception"
        assert user.password_hash.startswith("pbkdf2_sha256$")
        assert "reception" not in user.password_hash
        assert verifier_mot_de_passe("reception", user.password_hash)
        assert not verifier_mot_de_passe("autre", user.password_hash)
    assert len(JOURNAL_MONNIER) == 8


def test_login_protege_les_pages(client):
    assert client.get("/static/htmx.min.js").status_code == 200
    assert client.get("/static/tailwind.css").status_code == 200
    page = client.get("/login")
    assert page.status_code == 200
    assert "Panorama" in page.text
    assert "reception / reception" in page.text
    refuse = client.get("/dashboard", follow_redirects=False)
    assert refuse.status_code == 303
    assert refuse.headers["location"] == "/login"
    mauvais = client.post("/login", data={"identifiant": "reception", "password": "nope"})
    assert mauvais.status_code == 401
    assert "incorrect" in mauvais.text


def test_menu_puis_fiche_monnier(client):
    login(client)
    dashboard = client.get("/dashboard").text
    positions = [dashboard.index(libelle) for libelle in MENU]
    assert positions == sorted(positions)
    assert 'id="menu-detail" class="menu-link is-disabled" aria-disabled="true"' in dashboard

    sid = id_monnier(client.app)
    fiche = client.get(f"/sejours/{sid}")
    assert fiche.status_code == 200
    page = unescape(fiche.text)
    assert f'id="menu-detail" href="/sejours/{sid}"' in fiche.text
    assert 'aria-current="page"' in fiche.text
    for attendu in (
        "Monnier Christophe",
        "CLIENT PASSAGE",
        "WuBook",
        "En cours",
        "Double",
        "308",
        "27/10/2026",
        "28/10/2026",
        "61,20",
        "0 %",
        "4,00",
        "55,64",
        "5,56",
        "65,20",
        "0,00",
        "Lien de paiement",
        "Carte bancaire",
        "Espèces",
        "Chèques Vacances",
        "Total restant à payer",
        "Téléphone fixe",
        "Téléphone mobile",
        "+33 0678157017",
        "chris.tem@sfr.fr",
        "1793102243",
        "1793102243 ( WuBook )",
        NOTES_MONNIER,
        "Facturer",
        "Confirmer",
        "Abandon",
    ):
        assert attendu in page
    assert 'id="compte-reservations">(1)</span>' in fiche.text
    assert 'id="compte-reglements">(2)</span>' in fiche.text
    assert 'id="compte-modifications">(8)</span>' in fiche.text

    reglements = client.get(f"/sejours/{sid}?onglet=reglements").text
    balise = re.search(r'<div id="panneau-reglements"([^>]*)>', reglements)
    assert balise and "hidden" not in balise.group(1)
    reservations = re.search(r'<div id="panneau-reservations"([^>]*)>', reglements)
    assert reservations and "hidden" in reservations.group(1)

    contacts = client.get(f"/sejours/{sid}?bloc=contacts").text
    bloc = re.search(r'<div id="bloc-contacts"([^>]*)>', contacts)
    assert bloc and "hidden" not in bloc.group(1)
    notes = re.search(r'<div id="bloc-notes"([^>]*)>', contacts)
    assert notes and "hidden" in notes.group(1)

    retour = client.get("/dashboard").text
    assert f'id="menu-detail" href="/sejours/{sid}"' in retour
    assert "aria-disabled" not in retour


def test_reglement_statut_et_facture(client):
    login(client)
    sid = id_monnier(client.app)
    page = client.get(f"/sejours/{sid}").text
    token = jeton(page)
    partiel = client.post(
        f"/sejours/{sid}/reglements",
        data={"csrf": token, "montant": "10,50", "type_reglement": "Espèces"},
        headers={"HX-Request": "true"},
    )
    assert partiel.status_code == 200
    assert "<html" not in partiel.text.lower()
    assert "Espèces" in partiel.text
    assert "10,50" in partiel.text

    statut = client.post(
        f"/sejours/{sid}/statut",
        data={"csrf": token, "traite": "1"},
        headers={"HX-Request": "true"},
    )
    assert 'name="traite" value="1"' in statut.text
    assert "checked" in statut.text

    with Session(client.app.state.engine) as session:
        sejour = session.get(Sejour, sid)
        assert sejour is not None
        donnees = {
            "csrf": token,
            "action": "facturer",
            "nom": sejour.nom,
            "client_id": str(sejour.client_id),
            "pays_nat": "France",
            "partenaire": sejour.partenaire,
            "type_voiture": sejour.type_voiture,
            "date_facture": "",
            "num_facture": "",
            "telephone_fixe": sejour.telephone_fixe,
            "telephone_mobile": sejour.telephone_mobile,
            "fax": sejour.fax,
            "email": sejour.email,
            "ref_partenaire": sejour.ref_partenaire,
            "ref_distributeur": sejour.ref_distributeur,
            "notes": sejour.notes,
            "notes_internes": sejour.notes_internes,
            "notes_tempo": sejour.notes_tempo,
            "facturation_client": sejour.facturation_client,
        }
    facture = client.post(f"/sejours/{sid}/actions", data=donnees, follow_redirects=True)
    assert facture.status_code == 200
    assert "F-2026-" in facture.text
    assert "France" in facture.text
    assert "+33 0678157017" in facture.text


def test_abandon_desactive_le_menu(client):
    login(client)
    sid = id_monnier(client.app)
    client.get(f"/sejours/{sid}")
    token = jeton(client.get("/dashboard").text)
    retour = client.post(f"/sejours/{sid}/abandon", data={"csrf": token}, follow_redirects=False)
    assert retour.status_code == 303
    dashboard = client.get("/dashboard").text
    assert 'id="menu-detail" class="menu-link is-disabled" aria-disabled="true"' in dashboard


def test_planning_listes_et_logout(client):
    login(client)
    planning = client.get("/planning?debut=2026-10-25")
    assert "Monnier Christophe" in planning.text
    assert "308" in planning.text
    assert "Bernard Alain" in client.get("/sejours").text
    assert "Martin Sophie" in client.get("/sejours").text
    assert "Traité" in client.get("/sejours").text
    assert "CLIENT PASSAGE" in client.get("/clients").text
    assert "Petit-déjeuner" in client.get("/produits").text
    assert "Hôtel Panorama" in client.get("/parametres").text
    assert "SQLite" in client.get("/parametres").text

    token = jeton(client.get("/chambres").text)
    ajout = client.post(
        "/chambres",
        data={"csrf": token, "numero": "401", "type_chambre": "Twin", "etat": "pret"},
        follow_redirects=True,
    )
    assert "401" in ajout.text

    token = jeton(client.get("/dashboard").text)
    sortie = client.post("/logout", data={"csrf": token}, follow_redirects=False)
    assert sortie.status_code == 303
    assert sortie.headers["location"] == "/login"
    bloque = client.get("/sejours", follow_redirects=False)
    assert bloque.status_code == 303
