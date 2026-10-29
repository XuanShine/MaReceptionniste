from datetime import date

from ma_receptionniste.facturation import centimes
from ma_receptionniste.models import Client, Reservation
from ma_receptionniste.saisie import CHAMPS_FICHE

_VRAI = {"1", "on", "true", "True"}


def lire_date(texte: object) -> date | None:
    if texte is None:
        return None
    brut = str(texte).strip()
    if not brut:
        return None
    try:
        return date.fromisoformat(brut[:10])
    except ValueError:
        return None


def entier(texte: object, defaut: int | None = 0) -> int | None:
    if texte is None or str(texte).strip() == "":
        return defaut
    try:
        return int(str(texte).strip())
    except ValueError:
        return defaut


def montant(texte: object) -> int:
    if texte is None or str(texte).strip() == "":
        return 0
    return centimes(str(texte).strip().replace(" ", "").replace(",", "."))


def valeurs_fiche(form) -> dict:
    valeurs = {}
    for cle in CHAMPS_FICHE:
        if cle == "traitee":
            valeurs[cle] = str(form.get(cle) or "") in _VRAI
        else:
            valeurs[cle] = form.get(cle)
    return valeurs


def valeurs_enregistrees(fiche: dict) -> dict:
    sources = {Client: fiche["client"], Reservation: fiche["reservation"]}
    return {cle: sources[modele][cle] for cle, (modele, _) in CHAMPS_FICHE.items()}


def texte_champs(valeurs: dict) -> dict:
    return {cle: valeur if cle == "traitee" else ("" if valeur is None else valeur) for cle, valeur in valeurs.items()}
