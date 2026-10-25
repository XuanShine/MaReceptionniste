from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

from sqlmodel import Session, select

from ma_receptionniste.models import (
    Chambre,
    EtatChambre,
    HistoriqueMenage,
    Menage,
    Role,
    StatutMenage,
    TypeMenage,
    User,
)


class Action(StrEnum):
    voir = "voir"
    editer_liste = "editer_liste"
    retirer_en_cours = "retirer_en_cours"
    changer_statut = "changer_statut"
    gerer_chambres = "gerer_chambres"


DROITS: dict[Role, frozenset[Action]] = {
    Role.admin: frozenset(Action),
    Role.receptionniste: frozenset({Action.voir, Action.editer_liste}),
    Role.femme_de_chambre: frozenset({Action.voir, Action.changer_statut}),
}

LIBELLE_STATUT = {
    StatutMenage.a_faire: "À faire",
    StatutMenage.en_cours: "En cours",
    StatutMenage.fait: "Fait",
}
LIBELLE_TYPE = {
    TypeMenage.DEPART: "Départ",
    TypeMenage.RECOUCHE: "Recouche",
    TypeMenage.RECOUCHE_PLUS: "Recouche+",
    TypeMenage.AUTRE: "Autre",
}
LIBELLE_ROLE = {
    Role.admin: "Admin",
    Role.receptionniste: "Réceptionniste",
    Role.femme_de_chambre: "Femme de chambre",
}
LIBELLE_ETAT = {
    EtatChambre.pret: "Prête",
    EtatChambre.non_pret: "Non prête",
}
COULEUR_STATUT = {
    StatutMenage.a_faire.value: "warning",
    StatutMenage.en_cours.value: "secondary",
    StatutMenage.fait.value: "positive",
}


class DroitRefuse(PermissionError):
    pass


class MenageInconnu(LookupError):
    pass


class ChambreInconnue(LookupError):
    pass


class TypeMenageInvalide(ValueError):
    pass


class StatutMenageInvalide(ValueError):
    pass


class EtatInvalide(ValueError):
    pass


class NomChambreVide(ValueError):
    pass


@dataclass(frozen=True)
class Acteur:
    id: int
    nom: str
    role: Role


@dataclass(frozen=True)
class LigneMenage:
    id: int
    chambre_id: int
    chambre: str
    position: int
    type: str
    notes: str | None
    statut: str
    cree_par: str | None


@dataclass(frozen=True)
class LigneHistorique:
    id: int
    quand: datetime
    date: date
    chambre: str
    ancien: str
    nouveau: str
    auteur: str


@dataclass(frozen=True)
class LigneChambre:
    id: int
    nom: str
    type_chambre: str | None
    position: int
    etat: str


def autorise(acteur: Acteur, action: Action) -> bool:
    return action in DROITS[acteur.role]


def exiger(acteur: Acteur, action: Action) -> None:
    if not autorise(acteur, action):
        raise DroitRefuse(action.value)


def libelle_statut(valeur: str) -> str:
    try:
        return LIBELLE_STATUT[StatutMenage(valeur)]
    except ValueError:
        return valeur


def libelle_type(valeur: str) -> str:
    try:
        return LIBELLE_TYPE[TypeMenage(valeur)]
    except ValueError:
        return valeur


def jour_depuis(valeur: str | None, aujourd_hui: date | None = None) -> date:
    if valeur:
        try:
            return date.fromisoformat(valeur.strip()[:10])
        except ValueError:
            pass
    return aujourd_hui or date.today()


def poser_menage(
    session: Session,
    acteur: Acteur,
    jour: date,
    chambre_id: int,
    type_menage: str,
    notes: str | None,
) -> LigneMenage:
    exiger(acteur, Action.editer_liste)
    type_voulu = _type(type_menage)
    texte = _notes(notes)
    chambre = session.get(Chambre, chambre_id)
    if chambre is None:
        raise ChambreInconnue(chambre_id)
    menage = session.exec(select(Menage).where(Menage.jour == jour, Menage.chambre_id == chambre_id)).first()
    if menage is None:
        menage = Menage(
            jour=jour,
            chambre_id=chambre.id,
            type=type_voulu,
            notes=texte,
            statut=StatutMenage.a_faire,
            cree_par_id=acteur.id,
        )
        session.add(menage)
    elif _valeur(menage.type) == type_voulu.value and menage.notes == texte:
        return _ligne(session, menage)
    else:
        menage.type = type_voulu
        menage.notes = texte
        menage.modifie_par_id = acteur.id
        menage.modifie_le = datetime.now(UTC)
        session.add(menage)
    session.commit()
    session.refresh(menage)
    return _ligne(session, menage)


def retirer_menage(session: Session, acteur: Acteur, menage_id: int) -> None:
    menage = session.get(Menage, menage_id)
    if menage is None:
        raise MenageInconnu(menage_id)
    if _valeur(menage.statut) == StatutMenage.a_faire.value:
        exiger(acteur, Action.editer_liste)
    else:
        exiger(acteur, Action.retirer_en_cours)
    session.delete(menage)
    session.commit()


def changer_statut(session: Session, acteur: Acteur, menage_id: int, statut: str) -> LigneMenage:
    exiger(acteur, Action.changer_statut)
    nouveau = _statut(statut)
    menage = session.get(Menage, menage_id)
    if menage is None:
        raise MenageInconnu(menage_id)
    ancien = _valeur(menage.statut)
    if ancien == nouveau.value:
        return _ligne(session, menage)
    chambre = session.get(Chambre, menage.chambre_id)
    session.add(
        HistoriqueMenage(
            menage_id=menage.id,
            user_id=acteur.id,
            auteur_nom=acteur.nom,
            chambre_nom=chambre.nom if chambre else "",
            jour=menage.jour,
            ancien_statut=ancien,
            nouveau_statut=nouveau.value,
            quand=datetime.now(UTC),
        )
    )
    menage.statut = nouveau
    menage.modifie_par_id = acteur.id
    menage.modifie_le = datetime.now(UTC)
    session.add(menage)
    session.commit()
    session.refresh(menage)
    return _ligne(session, menage)


def lister_menages(session: Session, acteur: Acteur, jour: date) -> list[LigneMenage]:
    exiger(acteur, Action.voir)
    lignes = session.exec(select(Menage).where(Menage.jour == jour)).all()
    resultat = [_ligne(session, menage) for menage in lignes]
    return sorted(resultat, key=lambda ligne: (ligne.position, ligne.chambre))


def lister_historique(session: Session, acteur: Acteur, jour: date | None = None) -> list[LigneHistorique]:
    exiger(acteur, Action.voir)
    requete = select(HistoriqueMenage).order_by(HistoriqueMenage.quand.desc(), HistoriqueMenage.id.desc())
    if jour is not None:
        requete = requete.where(HistoriqueMenage.jour == jour)
    return [
        LigneHistorique(
            id=ligne.id or 0,
            quand=ligne.quand,
            date=ligne.jour,
            chambre=ligne.chambre_nom,
            ancien=ligne.ancien_statut,
            nouveau=ligne.nouveau_statut,
            auteur=ligne.auteur_nom,
        )
        for ligne in session.exec(requete).all()
    ]


def lister_chambres(session: Session, acteur: Acteur) -> list[LigneChambre]:
    exiger(acteur, Action.voir)
    chambres = session.exec(select(Chambre).order_by(Chambre.position, Chambre.nom)).all()
    return [
        LigneChambre(
            id=chambre.id or 0,
            nom=chambre.nom,
            type_chambre=chambre.type_chambre,
            position=chambre.position,
            etat=_valeur(chambre.etat),
        )
        for chambre in chambres
    ]


def creer_chambre(
    session: Session,
    acteur: Acteur,
    nom: str,
    position: int,
    type_chambre: str | None = None,
) -> int:
    exiger(acteur, Action.gerer_chambres)
    nom_propre = nom.strip()
    if not nom_propre:
        raise NomChambreVide(nom)
    chambre = Chambre(nom=nom_propre, position=position, type_chambre=_notes(type_chambre))
    session.add(chambre)
    session.commit()
    session.refresh(chambre)
    assert chambre.id is not None
    return chambre.id


def definir_etat(session: Session, acteur: Acteur, chambre_id: int, etat: str) -> None:
    exiger(acteur, Action.gerer_chambres)
    try:
        valeur = EtatChambre(etat)
    except ValueError:
        raise EtatInvalide(etat) from None
    chambre = session.get(Chambre, chambre_id)
    if chambre is None:
        raise ChambreInconnue(chambre_id)
    if _valeur(chambre.etat) == valeur.value:
        return
    chambre.etat = valeur
    session.add(chambre)
    session.commit()


def _type(valeur: str) -> TypeMenage:
    try:
        return TypeMenage(valeur)
    except ValueError:
        raise TypeMenageInvalide(valeur) from None


def _statut(valeur: str) -> StatutMenage:
    try:
        return StatutMenage(valeur)
    except ValueError:
        raise StatutMenageInvalide(valeur) from None


def _notes(valeur: str | None) -> str | None:
    if valeur is None:
        return None
    texte = valeur.strip()
    return texte or None


def _valeur(valeur: StrEnum | str) -> str:
    return valeur.value if isinstance(valeur, StrEnum) else str(valeur)


def _ligne(session: Session, menage: Menage) -> LigneMenage:
    chambre = session.get(Chambre, menage.chambre_id)
    createur = session.get(User, menage.cree_par_id) if menage.cree_par_id else None
    assert menage.id is not None
    return LigneMenage(
        id=menage.id,
        chambre_id=menage.chambre_id,
        chambre=chambre.nom if chambre else "",
        position=chambre.position if chambre else 0,
        type=_valeur(menage.type),
        notes=menage.notes,
        statut=_valeur(menage.statut),
        cree_par=createur.nom if createur else None,
    )
