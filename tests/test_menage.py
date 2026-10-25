from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from ma_gouvernante.comptes import COMPTES, MOT_DE_PASSE, assurer_comptes
from ma_gouvernante.menage import (
    Acteur,
    ChambreInconnue,
    DroitRefuse,
    MenageInconnu,
    StatutMenageInvalide,
    TypeMenageInvalide,
    changer_statut,
    creer_chambre,
    definir_etat,
    lister_historique,
    lister_menages,
    poser_menage,
    retirer_menage,
)
from ma_receptionniste.auth import authenticate, register_user
from ma_receptionniste.models import Chambre, HistoriqueMenage, Menage, Role, TypeMenage, User

JOUR = date(2026, 10, 25)


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _activer_cles_etrangeres(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    with Session(engine) as ouvert:
        yield ouvert


def _acteur(session: Session, role: Role, email: str, nom: str) -> Acteur:
    user = register_user(session, email, nom, "secret", role=role)
    return Acteur(id=user.id, nom=user.nom, role=Role(user.role))


@pytest.fixture
def monde(session: Session):
    douze = Chambre(nom="12", position=2)
    dix = Chambre(nom="10", position=1)
    session.add(douze)
    session.add(dix)
    session.commit()
    session.refresh(douze)
    session.refresh(dix)
    return SimpleNamespace(
        admin=_acteur(session, Role.admin, "admin@hotel.test", "Admin"),
        reception=_acteur(session, Role.receptionniste, "reception@hotel.test", "Léa"),
        femme=_acteur(session, Role.femme_de_chambre, "femme@hotel.test", "Camille"),
        douze=douze,
        dix=dix,
    )


def test_poser_cree_un_depart_sans_notes(session: Session, monde) -> None:
    ligne = poser_menage(session, monde.reception, JOUR, monde.douze.id, "DEPART", "  ")

    assert ligne.chambre == "12"
    assert ligne.type == "DEPART"
    assert ligne.notes is None
    assert ligne.statut == "a_faire"
    assert ligne.cree_par == "Léa"
    assert session.get(Menage, ligne.id).type == TypeMenage.DEPART


def test_reposer_la_meme_chambre_met_a_jour_sans_dupliquer(session: Session, monde) -> None:
    premiere = poser_menage(session, monde.reception, JOUR, monde.douze.id, "DEPART", None)
    changer_statut(session, monde.femme, premiere.id, "en_cours")

    seconde = poser_menage(session, monde.reception, JOUR, monde.douze.id, "RECOUCHE+", "Late checkout")
    identique = poser_menage(session, monde.reception, JOUR, monde.douze.id, "RECOUCHE+", "Late checkout")

    assert seconde.id == premiere.id == identique.id
    assert seconde.type == "RECOUCHE+"
    assert seconde.notes == "Late checkout"
    assert seconde.statut == "en_cours"
    assert len(session.exec(select(Menage)).all()) == 1


def test_type_inconnu_refuse(session: Session, monde) -> None:
    with pytest.raises(TypeMenageInvalide):
        poser_menage(session, monde.reception, JOUR, monde.douze.id, "SUITE", None)


def test_chambre_inconnue_refuse(session: Session, monde) -> None:
    with pytest.raises(ChambreInconnue):
        poser_menage(session, monde.reception, JOUR, 999, "DEPART", None)


def test_liste_triee_par_position(session: Session, monde) -> None:
    poser_menage(session, monde.reception, JOUR, monde.douze.id, "AUTRE", "draps")
    poser_menage(session, monde.admin, JOUR, monde.dix.id, "RECOUCHE", None)

    assert [ligne.chambre for ligne in lister_menages(session, monde.femme, JOUR)] == ["10", "12"]


def test_changement_de_statut_ecrit_l_historique(session: Session, monde) -> None:
    ligne = poser_menage(session, monde.reception, JOUR, monde.dix.id, "DEPART", None)

    changer_statut(session, monde.femme, ligne.id, "en_cours")
    changer_statut(session, monde.femme, ligne.id, "en_cours")
    changer_statut(session, monde.admin, ligne.id, "fait")

    historique = lister_historique(session, monde.reception, JOUR)
    assert [(ligne.ancien, ligne.nouveau, ligne.auteur, ligne.chambre) for ligne in historique] == [
        ("en_cours", "fait", "Admin", "10"),
        ("a_faire", "en_cours", "Camille", "10"),
    ]
    assert historique[0].quand >= historique[1].quand
    assert lister_historique(session, monde.femme, JOUR + timedelta(days=1)) == []
    assert len(session.exec(select(HistoriqueMenage)).all()) == 2


def test_statut_inconnu_ou_menage_inconnu(session: Session, monde) -> None:
    ligne = poser_menage(session, monde.reception, JOUR, monde.dix.id, "DEPART", None)
    with pytest.raises(StatutMenageInvalide):
        changer_statut(session, monde.femme, ligne.id, "abandonne")
    with pytest.raises(MenageInconnu):
        changer_statut(session, monde.femme, 999, "fait")


def test_droits_de_la_liste_et_du_statut(session: Session, monde) -> None:
    with pytest.raises(DroitRefuse):
        poser_menage(session, monde.femme, JOUR, monde.dix.id, "DEPART", None)
    ligne = poser_menage(session, monde.reception, JOUR, monde.dix.id, "DEPART", None)
    with pytest.raises(DroitRefuse):
        changer_statut(session, monde.reception, ligne.id, "fait")
    with pytest.raises(DroitRefuse):
        retirer_menage(session, monde.femme, ligne.id)

    changer_statut(session, monde.femme, ligne.id, "en_cours")
    with pytest.raises(DroitRefuse):
        retirer_menage(session, monde.reception, ligne.id)
    retirer_menage(session, monde.admin, ligne.id)

    assert lister_menages(session, monde.admin, JOUR) == []
    assert lister_historique(session, monde.admin, JOUR)[0].chambre == "10"


def test_reception_retire_un_menage_a_faire(session: Session, monde) -> None:
    ligne = poser_menage(session, monde.reception, JOUR, monde.dix.id, "DEPART", None)
    retirer_menage(session, monde.reception, ligne.id)
    assert lister_menages(session, monde.reception, JOUR) == []
    with pytest.raises(MenageInconnu):
        retirer_menage(session, monde.admin, ligne.id)


def test_admin_gere_les_chambres_les_autres_non(session: Session, monde) -> None:
    with pytest.raises(DroitRefuse):
        creer_chambre(session, monde.reception, "14", 3, "Double")
    with pytest.raises(DroitRefuse):
        definir_etat(session, monde.femme, monde.dix.id, "pret")

    chambre_id = creer_chambre(session, monde.admin, " 14 ", 3, " Double ")
    definir_etat(session, monde.admin, chambre_id, "pret")
    definir_etat(session, monde.admin, chambre_id, "pret")

    chambre = session.get(Chambre, chambre_id)
    assert chambre.nom == "14"
    assert chambre.type_chambre == "Double"
    assert str(chambre.etat) == "pret"


def test_comptes_demo_idempotents_sans_ecraser_un_compte_existant(session: Session) -> None:
    register_user(session, "reception@hotel-panorama.fr", "Existante", "autre-secret", role=Role.admin)

    assurer_comptes(session)
    assurer_comptes(session)

    comptes = session.exec(select(User)).all()
    assert {compte.email for compte in comptes} == {email for email, _nom, _role in COMPTES}
    reception = authenticate(session, "reception@hotel-panorama.fr", "autre-secret")
    assert reception.role == Role.admin
    assert authenticate(session, "reception@hotel-panorama.fr", MOT_DE_PASSE) is None
    assert authenticate(session, "admin@hotel-panorama.fr", MOT_DE_PASSE).role == Role.admin
    assert authenticate(session, "femme@hotel-panorama.fr", MOT_DE_PASSE).role == Role.femme_de_chambre
