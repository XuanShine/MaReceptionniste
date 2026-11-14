from ma_gouvernante.models import Role

_DROITS: dict[Role, frozenset[str]] = {
    Role.admin: frozenset({"gerer_chambres", "creer_liste", "changer_menage", "signaler", "resoudre"}),
    Role.receptionniste: frozenset({"creer_liste", "signaler", "resoudre"}),
    Role.femme_de_chambre: frozenset({"changer_menage", "signaler", "resoudre"}),
    Role.technicien: frozenset({"signaler", "resoudre"}),
}


class Refus(PermissionError):
    def __init__(self, action: str) -> None:
        super().__init__(action)
        self.action = action


def peut(role: Role | str, action: str) -> bool:
    try:
        role_connu = Role(role)
    except ValueError:
        return False
    return action in _DROITS.get(role_connu, frozenset())


def exiger(role: Role | str, action: str) -> None:
    if not peut(role, action):
        raise Refus(action)
