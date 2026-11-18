import math
import os
from collections import Counter
from xmlrpc.client import Error as XmlRpcError

from handling_rooms import HandlingRooms, Room
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import delete, select, update

from ma_receptionniste.db import get_session
from ma_receptionniste.models import Chambre, ChambreChambreVirtuelle, ChambreVirtuelle, TypeChambre


class ImportWubookImpossible(ValueError):
    """L'import a échoué ; le catalogue local reste inchangé."""


def mettre_a_jour_types_wubook() -> tuple[int, int]:
    """Remplace le catalogue local, sans écrire sur le serveur Wubook."""
    client = HandlingRooms()
    client.token = os.environ.get("WUBOOK_TOKEN")
    client.lcode = os.environ.get("WUBOOK_LCODE")
    if not client.token or not client.lcode:
        raise ImportWubookImpossible("Configurez WUBOOK_TOKEN et WUBOOK_LCODE avant la mise à jour")
    try:
        rooms = client.fetch_rooms()
    except (OSError, XmlRpcError, ValidationError) as erreur:
        raise ImportWubookImpossible("Impossible de récupérer les chambres Wubook. Aucune donnée modifiée.") from erreur
    finally:
        # Le context manager du paquet libère le token et dépend de returnCode, absent ici.
        client.server("close")()

    _valider_catalogue(rooms)
    reels = [room for room in rooms if not room.virtual]
    virtuels = [room for room in rooms if room.virtual]
    try:
        with get_session() as session:
            anciens = {type_.id: type_.wubook_id for type_ in session.exec(select(TypeChambre))}
            anciennes_virtuelles = {
                virtuelle.id: virtuelle.wubook_id for virtuelle in session.exec(select(ChambreVirtuelle))
            }
            chambres = list(session.exec(select(Chambre)))
            affectations = {chambre.id: anciens.get(chambre.type_chambre_id) for chambre in chambres}
            liens = [
                (lien.chambre_id, anciennes_virtuelles[lien.chambre_virtuelle_id])
                for lien in session.exec(select(ChambreChambreVirtuelle))
            ]
            _refuser_affectations_ambigues(anciens.values(), affectations.values())
            _refuser_affectations_ambigues(anciennes_virtuelles.values(), (wubook_id for _, wubook_id in liens))
            session.exec(update(Chambre).values(type_chambre_id=None))
            session.exec(delete(ChambreVirtuelle))
            session.exec(delete(TypeChambre))

            nouveaux = {}
            for room in reels:
                type_ = TypeChambre(
                    wubook_id=room.id,
                    libelle=room.name.strip(),
                    disponibilite=room.availability,
                    nom_raccourci=room.shortname.strip(),
                    prix_defaut=room.price,
                    prix_mini=room.min_price,
                    channel_manager_uniquement=bool(room.woodoo),
                )
                session.add(type_)
                nouveaux[room.id] = type_
            session.flush()
            nouvelles_virtuelles = {}
            for room in virtuels:
                virtuelle = ChambreVirtuelle(
                    wubook_id=room.id,
                    type_chambre_id=nouveaux[room.subroom].id,
                    nom_raccourci=room.shortname.strip(),
                    prix_defaut=room.price,
                    prix_mini=room.min_price,
                )
                session.add(virtuelle)
                nouvelles_virtuelles[room.id] = virtuelle
            session.flush()
            for chambre_id, wubook_id in liens:
                virtuelle = nouvelles_virtuelles.get(wubook_id)
                if virtuelle is not None:
                    session.add(ChambreChambreVirtuelle(chambre_id=chambre_id, chambre_virtuelle_id=virtuelle.id))
            for chambre in chambres:
                type_ = nouveaux.get(affectations[chambre.id])
                chambre.type_chambre_id = type_.id if type_ is not None else None
                session.add(chambre)
            session.commit()
    except IntegrityError as erreur:
        raise ImportWubookImpossible(
            "Le catalogue Wubook ne respecte pas les contraintes locales. Aucune donnée modifiée."
        ) from erreur
    return len(reels), len(virtuels)


def _refuser_affectations_ambigues(identifiants, affectations) -> None:
    occurrences = Counter(identifiant for identifiant in identifiants if identifiant is not None)
    if any(identifiant is not None and occurrences[identifiant] > 1 for identifiant in affectations):
        raise ImportWubookImpossible(
            "Des affectations possèdent un identifiant Wubook ambigu dans le catalogue local. Aucune donnée modifiée."
        )


def _valider_catalogue(rooms: list[Room]) -> None:
    ids, libelles, raccourcis = set(), set(), set()
    parents = {room.id for room in rooms if not room.virtual}
    for room in rooms:
        libelle, raccourci = room.name.strip(), room.shortname.strip()
        if (
            room.id <= 0
            or room.id in ids
            or not libelle
            or not 1 <= len(raccourci) <= 4
            or raccourci in raccourcis
            or room.woodoo not in (0, 1)
            or any(not math.isfinite(prix) or prix < 0 for prix in (room.price, room.min_price))
            or (room.virtual and room.subroom not in parents)
            or (not room.virtual and libelle in libelles)
        ):
            raise ImportWubookImpossible("Le catalogue Wubook est incohérent. Aucune donnée modifiée.")
        ids.add(room.id)
        raccourcis.add(raccourci)
        if not room.virtual:
            libelles.add(libelle)
