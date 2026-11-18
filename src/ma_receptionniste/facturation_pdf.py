"""PDF d'aperçu, non archivé, et PDF définitif écrit une seule fois par numéro."""

import fcntl
import hashlib
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from ma_receptionniste.db import get_session
from ma_receptionniste.facturation import ApercuFacture, PdfIndisponible, lire_facture
from ma_receptionniste.facturation_odt import contexte_apercu, contexte_facture, convertir_pdf, rendre_odt
from ma_receptionniste.models import Facture as FactureTable


def dossier_factures() -> Path:
    chemin = Path(os.environ.get("FACTURES_DIR", "data/factures"))
    chemin.mkdir(parents=True, exist_ok=True)
    return chemin


def generer_pdf_apercu(apercu: ApercuFacture) -> bytes:
    """PDF provisoire en mémoire. Aucun fichier d'archive, aucun numéro."""
    with tempfile.TemporaryDirectory(prefix="apercu-facture-") as dossier:
        racine = Path(dossier)
        odt = rendre_odt(contexte_apercu(apercu), racine / "apercu.odt")
        return convertir_pdf(odt, racine).read_bytes()


def generer_pdf(facture_id: int) -> Path:
    """Sert l'archive. La première écriture est verrouillée. Une archive connue manquante n'est pas réécrite."""
    with _verrou_facture(facture_id):
        facture = lire_facture(facture_id)
        if facture is None:
            raise PdfIndisponible("Facture introuvable")
        chemin = dossier_factures() / f"facture-{facture.numero}.pdf"
        if chemin.is_file():
            return _verifier_archive(facture_id, facture.pdf_empreinte, chemin)
        if facture.pdf_empreinte:
            raise PdfIndisponible(
                f"L'archive facture-{facture.numero}.pdf est absente. Restaurez ce fichier avant de le régénérer."
            )
        return _produire(facture_id, facture, chemin)


def _produire(facture_id: int, facture, chemin: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix="facture-pdf-") as dossier:
        racine = Path(dossier)
        odt = rendre_odt(contexte_facture(facture), racine / f"facture-{facture.numero}.odt")
        produit = convertir_pdf(odt, racine)
        data = produit.read_bytes()
    temporaire = chemin.with_name(f".{chemin.stem}.{uuid4().hex}.pdf")
    temporaire.write_bytes(data)
    os.replace(temporaire, chemin)
    _noter_pdf(facture_id, chemin, hashlib.sha256(data).hexdigest())
    return chemin


def _verifier_archive(facture_id: int, empreinte_connue: str | None, chemin: Path) -> Path:
    empreinte = hashlib.sha256(chemin.read_bytes()).hexdigest()
    if empreinte_connue and empreinte != empreinte_connue:
        raise PdfIndisponible("Le PDF archivé a été modifié")
    if not empreinte_connue:
        _noter_pdf(facture_id, chemin, empreinte)
    return chemin


@contextmanager
def _verrou_facture(facture_id: int):
    verrou = dossier_factures() / f"facture-{facture_id}.lock"
    with verrou.open("a") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _noter_pdf(facture_id: int, chemin: Path, empreinte: str) -> None:
    with get_session() as session:
        facture = session.get(FactureTable, facture_id)
        if facture is None:
            raise PdfIndisponible("Facture introuvable")
        facture.pdf_chemin = chemin.name
        facture.pdf_empreinte = empreinte
        session.add(facture)
        session.commit()
