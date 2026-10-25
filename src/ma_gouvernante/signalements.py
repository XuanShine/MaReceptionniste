import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlmodel import select

from ma_gouvernante.auth import utilisateur
from ma_gouvernante.chambres import ChambreIntrouvable
from ma_gouvernante.db import get_session
from ma_gouvernante.droits import exiger
from ma_gouvernante.journal import ajouter
from ma_gouvernante.models import Chambre, Signalement, StatutSignalement, User

TAILLE_MAX_OCTETS = 8 * 1024 * 1024


class NoteVide(ValueError):
    pass


class PhotoRefusee(ValueError):
    pass


class SignalementIntrouvable(ValueError):
    pass


def dossier_media() -> Path:
    return Path(os.environ.get("GOUVERNANTE_MEDIA", "data/gouvernante")).resolve()


def nettoyer_photos_partielles() -> None:
    dossier = dossier_media()
    if not dossier.is_dir():
        return
    for reste in dossier.glob(".*.part"):
        reste.unlink(missing_ok=True)


def _extension(contenu: bytes, nom: str | None) -> str:
    if len(contenu) > TAILLE_MAX_OCTETS:
        raise PhotoRefusee
    if contenu.startswith(b"\xff\xd8\xff"):
        ext, admis = ".jpg", {".jpg", ".jpeg"}
    elif contenu.startswith(b"\x89PNG\r\n\x1a\n"):
        ext, admis = ".png", {".png"}
    elif len(contenu) >= 12 and contenu.startswith(b"RIFF") and contenu[8:12] == b"WEBP":
        ext, admis = ".webp", {".webp"}
    else:
        raise PhotoRefusee
    if nom is not None and Path(nom).suffix.lower() not in admis:
        raise PhotoRefusee
    return ext


def _poser_photo(contenu: bytes, ext: str) -> Path:
    # Le fichier .part reste identifiable si le processus s'arrête avant le rename.
    dossier = dossier_media()
    dossier.mkdir(parents=True, exist_ok=True)
    final = dossier / f"{uuid4().hex}{ext}"
    temporaire = dossier / f".{final.name}.part"
    try:
        temporaire.write_bytes(contenu)
        temporaire.replace(final)
    except Exception:
        temporaire.unlink(missing_ok=True)
        raise
    return final


def ouvrir(
    user_id: int,
    chambre_id: int,
    note: str,
    contenu: bytes | None = None,
    nom: str | None = None,
) -> int:
    note = note.strip()
    if not note:
        raise NoteVide
    ext = _extension(contenu, nom) if contenu is not None else None
    with get_session() as session:
        user = utilisateur(session, user_id)
        exiger(user.role, "signaler")
        chambre = session.get(Chambre, chambre_id)
        if chambre is None:
            raise ChambreIntrouvable(chambre_id)
        chemin: Path | None = None
        try:
            if contenu is not None and ext is not None:
                chemin = _poser_photo(contenu, ext)
            signalement = Signalement(
                chambre_id=chambre.id,
                auteur_id=user.id,
                note=note,
                photo_path=str(chemin) if chemin is not None else None,
                statut=StatutSignalement.ouvert,
            )
            session.add(signalement)
            session.flush()
            ajouter(
                session,
                user.id,
                f"{user.nom} signale la chambre {chambre.nom}. {note}.",
                chambre_id=chambre.id,
                signalement_id=signalement.id,
            )
            signalement_id = signalement.id
            session.commit()
            return signalement_id
        except Exception:
            if chemin is not None:
                chemin.unlink(missing_ok=True)
            raise


def resoudre(user_id: int, signalement_id: int) -> None:
    with get_session() as session:
        user = utilisateur(session, user_id)
        exiger(user.role, "resoudre")
        signalement = session.get(Signalement, signalement_id)
        if signalement is None:
            raise SignalementIntrouvable(signalement_id)
        if StatutSignalement(signalement.statut) == StatutSignalement.resolu:
            return
        chambre = session.get(Chambre, signalement.chambre_id)
        nom_chambre = chambre.nom if chambre is not None else str(signalement.chambre_id)
        signalement.statut = StatutSignalement.resolu
        signalement.resolu_par_id = user_id
        signalement.resolu_le = datetime.now(UTC)
        ajouter(
            session,
            user.id,
            f"{user.nom} résout le signalement de la chambre {nom_chambre}.",
            chambre_id=signalement.chambre_id,
            signalement_id=signalement.id,
        )
        session.commit()


def lister_ouverts(chambre_id: int | None = None) -> list[dict]:
    with get_session() as session:
        requete = (
            select(Signalement, Chambre, User)
            .join(Chambre, Chambre.id == Signalement.chambre_id)
            .join(User, User.id == Signalement.auteur_id)
            .where(Signalement.statut == StatutSignalement.ouvert)
            .order_by(Signalement.cree_le, Signalement.id)
        )
        if chambre_id is not None:
            requete = requete.where(Signalement.chambre_id == chambre_id)
        lignes = session.exec(requete).all()
        return [
            {
                "id": signalement.id,
                "chambre_id": chambre.id,
                "chambre_nom": chambre.nom,
                "note": signalement.note,
                "auteur_nom": auteur.nom,
                "photo_path": signalement.photo_path,
                "cree_le": signalement.cree_le,
            }
            for signalement, chambre, auteur in lignes
        ]
