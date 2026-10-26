from fastapi import APIRouter, Request

from ma_receptionniste2.calendrier import lire_lundi
from ma_receptionniste2.lectures import semaine_planning
from ma_receptionniste2.web import SessionDB, Utilisateur, html, socle

router = APIRouter()


@router.get("/")
def planning(request: Request, session: SessionDB, user: Utilisateur, debut: str | None = None):
    aujourd_hui = request.app.state.aujourd_hui()
    lundi = lire_lundi(debut, aujourd_hui)
    semaine = semaine_planning(session, lundi, aujourd_hui)
    return html(request, "planning.html", socle(request, user, semaine=semaine, actif="/"))
