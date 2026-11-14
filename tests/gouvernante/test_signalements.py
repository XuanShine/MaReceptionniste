import os
from pathlib import Path

import pytest

from ma_gouvernante.chambres import creer_chambre
from ma_gouvernante.signalements import NoteVide, PhotoRefusee, lister_ouverts, ouvrir, resoudre

JPEG = b"\xff\xd8\xff\xd9"


def test_note_vide(compte) -> None:
    admin = compte("admin@hotel-panorama.fr")
    chambre_id = creer_chambre(admin["id"], "101", 1)
    with pytest.raises(NoteVide):
        ouvrir(admin["id"], chambre_id, "   ")
    assert lister_ouverts() == []


def test_note_sans_photo(compte) -> None:
    admin = compte("admin@hotel-panorama.fr")
    chambre_id = creer_chambre(admin["id"], "101", 1)
    ouvrir(admin["id"], chambre_id, "Ampoule cassée")
    ouverts = lister_ouverts()
    assert len(ouverts) == 1
    assert ouverts[0]["note"] == "Ampoule cassée"
    assert ouverts[0]["photo_path"] is None


def test_fichier_texte_refuse(compte) -> None:
    admin = compte("admin@hotel-panorama.fr")
    chambre_id = creer_chambre(admin["id"], "101", 1)
    media = Path(os.environ["GOUVERNANTE_MEDIA"])
    with pytest.raises(PhotoRefusee):
        ouvrir(admin["id"], chambre_id, "Fuite sous le lavabo", b"bonjour", "note.txt")
    assert lister_ouverts() == []
    assert list(media.iterdir()) == []


def test_resoudre_deux_fois(compte, descriptions) -> None:
    admin = compte("admin@hotel-panorama.fr")
    chambre_id = creer_chambre(admin["id"], "101", 1)
    signalement_id = ouvrir(admin["id"], chambre_id, "Poignée cassée")
    resoudre(admin["id"], signalement_id)
    avant = descriptions()
    resoudre(admin["id"], signalement_id)
    assert descriptions() == avant
    assert lister_ouverts() == []


def test_photo_presente_apres_ouvrir(compte) -> None:
    admin = compte("admin@hotel-panorama.fr")
    chambre_id = creer_chambre(admin["id"], "101", 1)
    ouvrir(admin["id"], chambre_id, "Tache au mur", JPEG, "photo.jpg")
    ouverts = lister_ouverts()
    assert len(ouverts) == 1
    chemin = Path(ouverts[0]["photo_path"])
    assert chemin.is_file()
    assert chemin.read_bytes() == JPEG


def test_photo_trop_grosse(compte) -> None:
    admin = compte("admin@hotel-panorama.fr")
    chambre_id = creer_chambre(admin["id"], "101", 1)
    media = Path(os.environ["GOUVERNANTE_MEDIA"])
    gros = b"\xff\xd8\xff" + b"0" * (8 * 1024 * 1024)
    with pytest.raises(PhotoRefusee):
        ouvrir(admin["id"], chambre_id, "Trop gros", gros, "photo.jpg")
    assert lister_ouverts() == []
    assert list(media.iterdir()) == []
