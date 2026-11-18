"""Envoi du PDF archivé. Sans serveur SMTP, l'envoi reste désactivé."""

import asyncio
import os
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage

from ma_receptionniste.db import get_session
from ma_receptionniste.facturation import EnvoiIndisponible, PdfIndisponible, lire_facture
from ma_receptionniste.facturation_pdf import generer_pdf
from ma_receptionniste.models import Historique


def envoi_configure() -> bool:
    return bool(os.environ.get("SMTP_HOST", "").strip())


def email_valide(email: str) -> bool:
    texte = email.strip()
    if texte.count("@") != 1 or any(caractere.isspace() for caractere in texte):
        return False
    local, domaine = texte.split("@")
    return bool(local) and "." in domaine and not domaine.startswith(".") and not domaine.endswith(".")


async def envoyer_facture(facture_id: int, email: str) -> None:
    await asyncio.to_thread(_envoyer, facture_id, email)


def _envoyer(facture_id: int, email: str) -> None:
    if not envoi_configure():
        raise EnvoiIndisponible("L'envoi par email n'est pas configuré")
    if not email_valide(email):
        raise EnvoiIndisponible("L'adresse email n'est pas valide")
    facture = lire_facture(facture_id)
    if facture is None:
        raise EnvoiIndisponible("Facture introuvable")
    try:
        chemin = generer_pdf(facture_id)
    except PdfIndisponible as erreur:
        raise EnvoiIndisponible(str(erreur)) from erreur
    message = EmailMessage()
    message["Subject"] = f"Facture n° {facture.numero}"
    message["From"] = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or "facturation@localhost"
    message["To"] = email.strip()
    message.set_content(f"Veuillez trouver la facture n° {facture.numero}.")
    message.add_attachment(chemin.read_bytes(), maintype="application", subtype="pdf", filename=chemin.name)
    try:
        _transmettre(message)
    except Exception as erreur:
        _journaliser(facture.sejour_id, f"Envoi de la facture n° {facture.numero} à {email.strip()} non confirmé")
        raise EnvoiIndisponible("L'envoi n'a pas été confirmé. Aucune nouvelle facture n'a été émise.") from erreur
    _journaliser(facture.sejour_id, f"Facture n° {facture.numero} envoyée à {email.strip()}")


def _transmettre(message: EmailMessage) -> None:
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=30) as client:
        if os.environ.get("SMTP_TLS", "1") != "0":
            client.starttls()
        utilisateur = os.environ.get("SMTP_USER", "").strip()
        if utilisateur:
            client.login(utilisateur, os.environ.get("SMTP_PASSWORD", ""))
        client.send_message(message)


def _journaliser(reservation_id: int, description: str) -> None:
    with get_session() as session:
        session.add(
            Historique(reservation_id=reservation_id, user_id=None, description=description, date=datetime.now(UTC))
        )
        session.commit()
