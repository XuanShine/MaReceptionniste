from collections.abc import Callable

from ma_gouvernante.models import Role

_cartes: list[dict] = []
_lien_chambre: Callable[[int], str] | None = None

_RANG = {
    "Chambres": 1,
    "Liste du jour": 2,
    "Signalements ouverts": 3,
    "Historique": 4,
}


def ajouter_carte(roles: tuple[Role, ...] | list[Role], titre: str, href: str) -> None:
    normalises = tuple(Role(role) for role in roles)
    for carte in _cartes:
        if carte["titre"] == titre and carte["href"] == href and carte["roles"] == normalises:
            return
    _cartes.append({"roles": normalises, "titre": titre, "href": href})


def cartes_pour(role: Role | str) -> list[dict[str, str]]:
    role_connu = Role(role)
    visibles = [carte for carte in _cartes if role_connu in carte["roles"]]

    def cle(carte: dict) -> tuple[int, int]:
        if role_connu == Role.technicien and carte["titre"] == "Signalements ouverts":
            return (0, 0)
        return (1, _RANG.get(carte["titre"], 9))

    return [{"titre": carte["titre"], "href": carte["href"]} for carte in sorted(visibles, key=cle)]


def lier_chambre(fabrique: Callable[[int], str]) -> None:
    global _lien_chambre
    _lien_chambre = fabrique


def lien_chambre(chambre_id: int) -> str | None:
    if _lien_chambre is None:
        return None
    return _lien_chambre(chambre_id)
