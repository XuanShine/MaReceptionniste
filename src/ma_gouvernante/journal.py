from sqlmodel import Session, select

from ma_gouvernante.db import get_session
from ma_gouvernante.models import Historique


def ajouter(
    session: Session,
    user_id: int,
    description: str,
    *,
    chambre_id: int | None = None,
    liste_id: int | None = None,
    signalement_id: int | None = None,
) -> None:
    session.add(
        Historique(
            user_id=user_id,
            chambre_id=chambre_id,
            liste_id=liste_id,
            signalement_id=signalement_id,
            description=description,
        )
    )


def lister() -> list[dict]:
    with get_session() as session:
        rows = session.exec(select(Historique).order_by(Historique.date.desc(), Historique.id.desc())).all()
        return [{"description": row.description, "date": row.date} for row in rows]
