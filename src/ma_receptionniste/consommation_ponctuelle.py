"""Consommations prises certains jours seulement, notées en YAML dans ``notes_internes``.

Aucune base ici : la fiche affiche, ``saisie.py`` écrit. Une note qu'on ne sait pas lire
lève ``NoteIllisible`` et ne doit jamais être réécrite.
"""

import copy
from collections.abc import Iterable
from datetime import date, timedelta

import yaml

# La clé de chambre dans la note. Le nom affiché remet un espace : « Chambre 12 ».
PREFIXE_CHAMBRE = "Chambre_"


class NoteIllisible(ValueError):
    """Le YAML de la note interne est invalide ou n'a pas la forme attendue."""


def cle_chambre(chambre: str) -> str:
    return f"{PREFIXE_CHAMBRE}{chambre}"


def nom_chambre(cle: str) -> str:
    if cle.startswith(PREFIXE_CHAMBRE):
        return cle[len(PREFIXE_CHAMBRE) :]
    return cle


def lire(note: str | None) -> dict:
    """Vide ou blanc donne ``{}``. Un YAML invalide ou mal formé lève ``NoteIllisible``."""
    if note is None or not note.strip():
        return {}
    try:
        charge = yaml.safe_load(note)
    except yaml.YAMLError as erreur:
        raise NoteIllisible("La note interne n'est pas un YAML lisible") from erreur
    if charge is None:
        return {}
    if not isinstance(charge, dict):
        raise NoteIllisible("La note interne n'est pas un YAML lisible")
    return _canonique(charge)


def ecrire(donnees: dict) -> str:
    """YAML stable : clés triées, dates ISO non quotées. Rien à noter donne une chaîne vide."""
    propre = _canonique(copy.deepcopy(donnees or {}))
    if not propre:
        return ""
    # PyYAML lit 2026-11-11 comme une date. On les garde : le dump reste non quoté, dans l'ordre.
    return yaml.safe_dump(propre, allow_unicode=True, sort_keys=True, default_flow_style=False, width=4096)


def jours_du_sejour(sejour: object) -> list[date]:
    """De ``date_debut`` à ``date_fin``, les deux incluses."""
    debut = _champ(sejour, "date_debut")
    fin = _champ(sejour, "date_fin")
    if fin < debut:
        return []
    return [debut + timedelta(days=ecart) for ecart in range((fin - debut).days + 1)]


def basculer(donnees: dict, chambre: str, produit: str, jour: date, nombre: int | None) -> dict:
    """Pose ``nombre`` ce jour-là. ``None`` retire la date, puis les branches devenues vides."""
    resultat = copy.deepcopy(donnees) if donnees else {}
    conso = resultat.setdefault("Consommation", {})
    produits = conso.setdefault(cle_chambre(chambre), {})
    jours = produits.setdefault(produit, {})
    if nombre is None:
        jours.pop(jour, None)
    else:
        jours[jour] = nombre
    return _nettoyer(resultat)


def tout_cocher(donnees: dict, chambre: str, produit: str, jours: Iterable[date], nombre: int) -> dict:
    resultat = copy.deepcopy(donnees) if donnees else {}
    for jour in jours:
        resultat = basculer(resultat, chambre, produit, jour, nombre)
    return resultat


def tout_retirer(donnees: dict, chambre: str, produit: str) -> dict:
    resultat = copy.deepcopy(donnees) if donnees else {}
    conso = resultat.get("Consommation")
    if isinstance(conso, dict):
        produits = conso.get(cle_chambre(chambre))
        if isinstance(produits, dict):
            produits.pop(produit, None)
    return _nettoyer(resultat)


def totaux(donnees: dict) -> dict[tuple[str, str], int]:
    """Somme des nombres par ``(Chambre_<nom>, produit)``."""
    resultat: dict[tuple[str, str], int] = {}
    for chambre, produits in (donnees.get("Consommation") or {}).items():
        for produit, jours in produits.items():
            resultat[(chambre, produit)] = sum(jours.values())
    return resultat


def incoherences(donnees: dict, sejours: Iterable[object]) -> list[str]:
    """Chambre absente des séjours courants, ou date cochée en dehors des dates de son séjour."""
    couverts = _jours_par_chambre(sejours)
    messages: list[str] = []
    for cle in sorted(donnees.get("Consommation") or {}):
        nom = nom_chambre(cle)
        produits = donnees["Consommation"][cle]
        if nom not in couverts:
            messages.extend(
                f"{produit} · Chambre {nom} : chambre absente des séjours" for produit in sorted(produits)
            )
            continue
        for produit in sorted(produits):
            messages.extend(
                f"{produit} · Chambre {nom} · {jour:%d/%m/%Y} : hors du séjour"
                for jour in sorted(produits[produit])
                if jour not in couverts[nom]
            )
    return messages


def _jours_par_chambre(sejours: Iterable[object]) -> dict[str, set[date]]:
    couverts: dict[str, set[date]] = {}
    for sejour in sejours:
        couverts.setdefault(_nom_sejour(sejour), set()).update(jours_du_sejour(sejour))
    return couverts


def _nom_sejour(sejour: object) -> str:
    if isinstance(sejour, dict):
        if "chambre_nom" in sejour:
            return sejour["chambre_nom"]
        chambre = sejour["chambre"]
        return chambre["nom"] if isinstance(chambre, dict) else chambre.nom
    nom = getattr(sejour, "chambre_nom", None)
    if nom is not None:
        return nom
    return sejour.chambre.nom


def _champ(sejour: object, nom: str) -> date:
    if isinstance(sejour, dict):
        return sejour[nom]
    return getattr(sejour, nom)


def _canonique(charge: dict) -> dict:
    resultat: dict = {}
    for cle, valeur in charge.items():
        if not isinstance(cle, str):
            raise NoteIllisible("La note interne n'est pas un YAML lisible")
        if cle == "Consommation":
            resultat[cle] = _canonique_consommation(valeur)
        else:
            resultat[cle] = valeur
    return _nettoyer(resultat)


def _canonique_consommation(valeur: object) -> dict:
    if valeur is None:
        return {}
    if not isinstance(valeur, dict):
        raise NoteIllisible("La note interne n'est pas un YAML lisible")
    chambres: dict = {}
    for cle, produits in valeur.items():
        if not isinstance(cle, str) or not isinstance(produits, dict):
            raise NoteIllisible("La note interne n'est pas un YAML lisible")
        propres: dict = {}
        for produit, jours in produits.items():
            if not isinstance(produit, str) or not isinstance(jours, dict):
                raise NoteIllisible("La note interne n'est pas un YAML lisible")
            propres[produit] = {_comme_date(jour): _comme_nombre(nombre) for jour, nombre in jours.items()}
        chambres[cle] = propres
    return chambres


def _comme_date(valeur: object) -> date:
    if type(valeur) is date:
        return valeur
    if isinstance(valeur, str):
        try:
            return date.fromisoformat(valeur)
        except ValueError:
            raise NoteIllisible("La note interne n'est pas un YAML lisible") from None
    raise NoteIllisible("La note interne n'est pas un YAML lisible")


def _comme_nombre(valeur: object) -> int:
    if isinstance(valeur, bool) or not isinstance(valeur, int):
        raise NoteIllisible("La note interne n'est pas un YAML lisible")
    return valeur


def _nettoyer(donnees: dict) -> dict:
    conso = donnees.get("Consommation")
    if isinstance(conso, dict):
        chambres = {}
        for cle, produits in conso.items():
            if not isinstance(produits, dict):
                continue
            propres = {produit: jours for produit, jours in produits.items() if isinstance(jours, dict) and jours}
            if propres:
                chambres[cle] = propres
        if chambres:
            donnees["Consommation"] = chambres
        else:
            donnees.pop("Consommation", None)
    return donnees
