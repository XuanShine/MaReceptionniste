"""Appel à HandlingRooms. Les tests remplacent le canal. Sans jeton, aucun appel ne part."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_RACINE = Path(__file__).resolve().parents[2]
load_dotenv(_RACINE / ".env")

_SANS_FORMULE = "nb"

_remplace = None
_remplace_actif = False


def installer(canal) -> None:
    global _remplace, _remplace_actif
    _remplace = canal
    _remplace_actif = True


def retirer() -> None:
    global _remplace, _remplace_actif
    _remplace = None
    _remplace_actif = False


def canal_actif():
    if _remplace_actif:
        return _remplace
    if not os.environ.get("WUBOOK_TOKEN") or not os.environ.get("WUBOOK_LCODE"):
        return None
    return _handling_rooms()


def creer_room(canal, *, parent_wubook_id: int | None, **champs) -> int:
    if parent_wubook_id:
        return canal.new_virtual_room(
            parent_id=parent_wubook_id,
            woodoo=champs["woodoo"],
            name=champs["name"],
            beds=champs["beds"],
            children=champs["children"],
            price=champs["price"],
            shortname=champs["shortname"],
            board=_SANS_FORMULE,
            dec_avail=champs["dec_avail"],
        )
    return canal.new_room(
        woodoo=champs["woodoo"],
        name=champs["name"],
        beds=champs["beds"],
        price=champs["price"],
        availability=champs["availability"],
        shortname=champs["shortname"],
        board=_SANS_FORMULE,
    )


def modifier_room(canal, *, wubook_id: int, parent_wubook_id: int | None, **champs) -> int:
    if parent_wubook_id:
        return canal.mod_virtual_room(
            wubook_id,
            name=champs["name"],
            beds=champs["beds"],
            children=champs["children"],
            price=champs["price"],
            shortname=champs["shortname"],
            board=_SANS_FORMULE,
            dec_avail=champs["dec_avail"],
        )
    return canal.mod_room(
        wubook_id,
        name=champs["name"],
        beds=champs["beds"],
        price=champs["price"],
        availability=champs["availability"],
        shortname=champs["shortname"],
        board=_SANS_FORMULE,
    )


def _handling_rooms():
    try:
        from handling_rooms import HandlingRooms
    except ImportError:
        racine = Path(__file__).resolve().parents[3] / "wubook"
        sys.path.insert(0, str(racine))
        from handling_rooms import HandlingRooms
    return HandlingRooms()
