from xmlrpc.client import Fault

import pytest
from handling_rooms import HandlingRooms, Room
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ma_receptionniste.db import create_db_and_tables
from ma_receptionniste.models import Chambre, ChambreChambreVirtuelle, ChambreVirtuelle, TypeChambre
from ma_receptionniste.wubook import ImportWubookImpossible, mettre_a_jour_types_wubook


def chambre_wubook(**changements) -> Room:
    return Room.model_validate(
        {
            "id": 123,
            "name": "Double Wubook",
            "shortname": "DBL",
            "occupancy": 2,
            "men": 2,
            "children": 0,
            "subroom": 0,
            "anchorate": 0,
            "price": 95.5,
            "availability": 4,
            "board": "nb",
            "woodoo": 1,
            "dec_avail": 0,
            "min_price": 55,
            "max_price": 0,
            "rtype": 1,
            "rtype_name": "Room",
            **changements,
        }
    )


@pytest.fixture
def serveur(monkeypatch):
    monkeypatch.setenv("WUBOOK_TOKEN", "token-test")
    monkeypatch.setenv("WUBOOK_LCODE", "123456")
    rooms = [
        # Le parent tarifaire est indépendant du parent de disponibilité.
        chambre_wubook(id=456, shortname="SGL", subroom=123, anchorate=789, price=75, min_price=45),
        chambre_wubook(),
        chambre_wubook(id=789, name="Suite", shortname="STE", woodoo=0),
    ]
    monkeypatch.setattr(HandlingRooms, "fetch_rooms", lambda self: rooms)
    return rooms


@pytest.fixture
def catalogue(base):
    with Session(base) as session:
        double = TypeChambre(wubook_id=123, libelle="Ancien double", nom_raccourci="OLD", prix_defaut=10)
        disparu = TypeChambre(wubook_id=999, libelle="Disparu")
        local = TypeChambre(libelle="Local")
        session.add_all([double, disparu, local])
        session.flush()
        session.add_all(
            [
                Chambre(nom="101", position=1, etage=2, type_chambre_id=double.id),
                Chambre(nom="102", position=2, type_chambre_id=disparu.id),
                Chambre(nom="103", position=3, type_chambre_id=local.id),
                Chambre(nom="104", position=4),
                ChambreVirtuelle(
                    type_chambre_id=double.id, wubook_id=888, nom_raccourci="OLDV", prix_defaut=10, prix_mini=5
                ),
            ]
        )
        session.commit()
    return base


@pytest.fixture
def catalogue_avec_liens(catalogue):
    with Session(catalogue) as session:
        double = session.exec(select(TypeChambre).where(TypeChambre.wubook_id == 123)).one()
        chambres = list(session.exec(select(Chambre).order_by(Chambre.position)))
        virtuelle_disparue = session.exec(select(ChambreVirtuelle)).one()
        partagee = ChambreVirtuelle(
            type_chambre_id=double.id, wubook_id=456, nom_raccourci="V456", prix_defaut=10, prix_mini=5
        )
        autre = ChambreVirtuelle(
            type_chambre_id=double.id, wubook_id=457, nom_raccourci="V457", prix_defaut=10, prix_mini=5
        )
        locale = ChambreVirtuelle(type_chambre_id=double.id, nom_raccourci="LOC", prix_defaut=10, prix_mini=5)
        session.add_all([partagee, autre, locale])
        session.flush()
        session.add_all(
            [
                ChambreChambreVirtuelle(chambre_id=chambres[0].id, chambre_virtuelle_id=partagee.id),
                ChambreChambreVirtuelle(chambre_id=chambres[1].id, chambre_virtuelle_id=partagee.id),
                ChambreChambreVirtuelle(chambre_id=chambres[0].id, chambre_virtuelle_id=autre.id),
                ChambreChambreVirtuelle(chambre_id=chambres[2].id, chambre_virtuelle_id=virtuelle_disparue.id),
                ChambreChambreVirtuelle(chambre_id=chambres[3].id, chambre_virtuelle_id=locale.id),
            ]
        )
        session.commit()
    return catalogue


def instantane(base):
    with Session(base) as session:
        catalogue = [
            [
                {colonne.name: getattr(ligne, colonne.name) for colonne in modele.__table__.columns}
                for ligne in session.exec(select(modele).order_by(modele.id))
            ]
            for modele in (TypeChambre, ChambreVirtuelle, Chambre)
        ]
        liens = session.exec(
            select(ChambreChambreVirtuelle).order_by(
                ChambreChambreVirtuelle.chambre_id, ChambreChambreVirtuelle.chambre_virtuelle_id
            )
        )
        return [*catalogue, [(lien.chambre_id, lien.chambre_virtuelle_id) for lien in liens]]


def affectations_virtuelles(base):
    with Session(base) as session:
        return set(
            session.exec(
                select(Chambre.nom, ChambreVirtuelle.wubook_id)
                .join(ChambreChambreVirtuelle, ChambreChambreVirtuelle.chambre_id == Chambre.id)
                .join(ChambreVirtuelle, ChambreVirtuelle.id == ChambreChambreVirtuelle.chambre_virtuelle_id)
            ).all()
        )


def test_import_remplace_le_catalogue_et_retablit_les_affectations(catalogue, serveur):
    assert mettre_a_jour_types_wubook() == (2, 1)
    with Session(catalogue) as session:
        types = {type_.wubook_id: type_ for type_ in session.exec(select(TypeChambre))}
        assert set(types) == {123, 789}
        double = types[123]
        assert double.libelle == "Double Wubook"
        assert double.description == ""
        assert double.disponibilite == 4
        assert double.nom_raccourci == "DBL"
        assert double.prix_defaut == 95.5
        assert double.prix_mini == 55
        assert double.channel_manager_uniquement is True
        assert types[789].channel_manager_uniquement is False
        virtuelle = session.exec(select(ChambreVirtuelle)).one()
        assert virtuelle.wubook_id == 456
        assert virtuelle.type_chambre_id == double.id
        assert virtuelle.nom_raccourci == "SGL"
        assert virtuelle.description == ""
        assert virtuelle.prix_defaut == 75
        assert virtuelle.prix_mini == 45
        chambres = list(session.exec(select(Chambre).order_by(Chambre.position)))
        assert [chambre.nom for chambre in chambres] == ["101", "102", "103", "104"]
        assert [chambre.etage for chambre in chambres] == [2, 0, 0, 0]
        assert [chambre.type_chambre_id for chambre in chambres] == [double.id, None, None, None]

    # Une seconde mise à jour écrase aussi les modifications locales.
    with Session(catalogue) as session:
        double = session.exec(select(TypeChambre).where(TypeChambre.wubook_id == 123)).one()
        double.prix_defaut = 1
        session.add(double)
        session.commit()
    assert mettre_a_jour_types_wubook() == (2, 1)
    with Session(catalogue) as session:
        assert session.exec(select(TypeChambre).where(TypeChambre.wubook_id == 123)).one().prix_defaut == 95.5


def test_un_catalogue_distant_vide_vide_le_catalogue_local(catalogue, serveur):
    serveur.clear()
    assert mettre_a_jour_types_wubook() == (0, 0)
    types, virtuelles, chambres, liens = instantane(catalogue)
    assert types == virtuelles == []
    assert liens == []
    assert len(chambres) == 4
    assert all(chambre["type_chambre_id"] is None for chambre in chambres)


def test_import_conserve_partages_et_supprime_liens_locaux_ou_disparus(catalogue_avec_liens, serveur):
    serveur.append(chambre_wubook(id=457, shortname="VR57", subroom=123))
    attendues = {("101", 456), ("102", 456), ("101", 457)}

    for _ in range(2):
        assert mettre_a_jour_types_wubook() == (2, 2)
        assert affectations_virtuelles(catalogue_avec_liens) == attendues

    serveur.clear()
    assert mettre_a_jour_types_wubook() == (0, 0)
    assert affectations_virtuelles(catalogue_avec_liens) == set()


@pytest.mark.parametrize("catalogue_concerne", ["type", "virtuelle"])
def test_identifiant_local_ambigu_affecte_refuse_sans_modification(catalogue_avec_liens, serveur, catalogue_concerne):
    with Session(catalogue_avec_liens) as session:
        if catalogue_concerne == "type":
            session.add(TypeChambre(wubook_id=123, libelle="Doublon"))
        else:
            double = session.exec(select(TypeChambre).where(TypeChambre.wubook_id == 123)).one()
            session.add(
                ChambreVirtuelle(
                    type_chambre_id=double.id, wubook_id=456, nom_raccourci="DUP", prix_defaut=10, prix_mini=5
                )
            )
        session.commit()
    avant = instantane(catalogue_avec_liens)
    with pytest.raises(ImportWubookImpossible, match="ambigu"):
        mettre_a_jour_types_wubook()
    assert instantane(catalogue_avec_liens) == avant


def test_doublons_sans_affectation_ne_bloquent_pas_import(catalogue_avec_liens, serveur):
    with Session(catalogue_avec_liens) as session:
        session.add_all(
            [TypeChambre(wubook_id=321, libelle="Doublon 1"), TypeChambre(wubook_id=321, libelle="Doublon 2")]
        )
        double = session.exec(select(TypeChambre).where(TypeChambre.wubook_id == 123)).one()
        session.add_all(
            [
                ChambreVirtuelle(
                    type_chambre_id=double.id, wubook_id=654, nom_raccourci=nom, prix_defaut=10, prix_mini=5
                )
                for nom in ("DUP1", "DUP2")
            ]
        )
        session.commit()
    assert mettre_a_jour_types_wubook() == (2, 1)
    assert affectations_virtuelles(catalogue_avec_liens) == {("101", 456), ("102", 456)}


def test_echec_retablissement_liens_annule_import(catalogue_avec_liens, serveur):
    avant = instantane(catalogue_avec_liens)

    def echouer(*args):
        raise IntegrityError("insertion du lien refusée", {}, Exception("contrainte"))

    event.listen(ChambreChambreVirtuelle, "before_insert", echouer)
    try:
        with pytest.raises(ImportWubookImpossible, match="contraintes locales"):
            mettre_a_jour_types_wubook()
    finally:
        event.remove(ChambreChambreVirtuelle, "before_insert", echouer)
    assert instantane(catalogue_avec_liens) == avant


@pytest.mark.parametrize("erreur", [ConnectionError("indisponible"), Fault(1, "refus"), TimeoutError()])
def test_un_echec_distant_ne_touche_pas_aux_donnees(catalogue, serveur, monkeypatch, erreur):
    avant = instantane(catalogue)

    def echouer(self):
        raise erreur

    monkeypatch.setattr(HandlingRooms, "fetch_rooms", echouer)
    with pytest.raises(ImportWubookImpossible, match="Impossible de récupérer"):
        mettre_a_jour_types_wubook()
    assert instantane(catalogue) == avant


@pytest.mark.parametrize("variable", ["WUBOOK_TOKEN", "WUBOOK_LCODE"])
def test_configuration_manquante_sans_appel_distant(catalogue, serveur, monkeypatch, variable):
    monkeypatch.delenv(variable)

    def interdit(self):
        pytest.fail("Aucun appel distant sans configuration")

    monkeypatch.setattr(HandlingRooms, "fetch_rooms", interdit)
    avant = instantane(catalogue)
    with pytest.raises(ImportWubookImpossible, match="Configurez"):
        mettre_a_jour_types_wubook()
    assert instantane(catalogue) == avant


@pytest.mark.parametrize(
    "changements",
    [
        {"subroom": 999},
        {"id": 123},
        {"shortname": "DBL"},
        {"shortname": "LONGUE"},
        {"shortname": " "},
        {"price": float("nan")},
        {"price": float("inf")},
        {"price": -1},
        {"woodoo": 2},
        {"subroom": 0, "name": "Double Wubook"},
    ],
)
def test_catalogue_incoherent_refuse_avant_ecrasement(catalogue, serveur, changements):
    avant = instantane(catalogue)
    serveur[0] = serveur[0].model_copy(update=changements)
    with pytest.raises(ImportWubookImpossible, match="incohérent"):
        mettre_a_jour_types_wubook()
    assert instantane(catalogue) == avant


def test_echec_d_insertion_annule_aussi_les_suppressions(catalogue_avec_liens, serveur):
    avant = instantane(catalogue_avec_liens)

    def echouer(*args):
        raise IntegrityError("insertion refusée", {}, Exception("contrainte"))

    event.listen(ChambreVirtuelle, "before_insert", echouer)
    try:
        with pytest.raises(ImportWubookImpossible, match="contraintes locales"):
            mettre_a_jour_types_wubook()
    finally:
        event.remove(ChambreVirtuelle, "before_insert", echouer)
    assert instantane(catalogue_avec_liens) == avant


def test_import_apres_migration_d_une_cellule_virtuelle_historique(catalogue, serveur):
    with catalogue.begin() as connexion:
        assert connexion.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        connexion.exec_driver_sql(
            "CREATE TABLE option_virtuelle ("
            "id INTEGER PRIMARY KEY, nom VARCHAR NOT NULL UNIQUE, formule_prix VARCHAR NOT NULL)"
        )
        connexion.exec_driver_sql(
            "CREATE TABLE cellule_virtuelle ("
            "id INTEGER PRIMARY KEY, type_chambre_id INTEGER NOT NULL REFERENCES type_chambre(id), "
            "option_id INTEGER NOT NULL REFERENCES option_virtuelle(id), shortname VARCHAR NOT NULL UNIQUE)"
        )
        connexion.exec_driver_sql(
            "INSERT INTO option_virtuelle (id, nom, formule_prix) VALUES (1, 'Petit Déjeuner', 'x+10*p')"
        )
        connexion.exec_driver_sql(
            "INSERT INTO cellule_virtuelle (id, type_chambre_id, option_id, shortname) "
            "SELECT 1, id, 1, '2BBB' FROM type_chambre WHERE wubook_id=123"
        )

    # Reproduit exactement le blocage avant la migration.
    with pytest.raises(ImportWubookImpossible, match="contraintes locales"):
        mettre_a_jour_types_wubook()

    create_db_and_tables(catalogue)
    create_db_and_tables(catalogue)

    assert mettre_a_jour_types_wubook() == (2, 1)
    with Session(catalogue) as session:
        double = session.exec(select(TypeChambre).where(TypeChambre.wubook_id == 123)).one()
        assert session.exec(select(Chambre).where(Chambre.nom == "101")).one().type_chambre_id == double.id
        assert session.exec(select(ChambreVirtuelle)).one().wubook_id == 456
    with catalogue.connect() as connexion:
        assert connexion.exec_driver_sql(
            "SELECT shortname, type_chambre_wubook_id FROM archive_cellule_virtuelle"
        ).one() == ("2BBB", 123)
        assert connexion.exec_driver_sql("SELECT formule_prix FROM archive_option_virtuelle").scalar_one() == "x+10*p"
        assert connexion.exec_driver_sql("PRAGMA foreign_key_check").all() == []
