from datetime import date, timedelta

from fastapi import APIRouter, Request
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from ma_receptionniste.consultations import (
    charger_planning,
    charger_resume,
    lister_chambres,
    lister_clients,
    lister_reservations,
    options_clients,
)
from ma_receptionniste.saisie import (
    basculer_etat,
    creer_chambre,
    creer_client,
    creer_reservation,
    modifier_type_chambre,
)
from ma_receptionniste.web.formes import entier
from ma_receptionniste.web.rendu import cible, fragments, hx, page, rediriger, rendre
from ma_receptionniste.web.rendu import message as toast
from ma_receptionniste.web.vue import lundi_de, preparer_planning, preparer_reservations

router = APIRouter()


def _texte(form, cle: str) -> str:
    return str(form.get(cle) or "")


@router.get("/")
async def planning(request: Request, lundi: date | None = None):
    aujourd_hui = date.today()
    debut = lundi_de(lundi or aujourd_hui)
    data = await run_in_threadpool(charger_planning, debut, debut + timedelta(days=7))
    vue = preparer_planning(debut, aujourd_hui, data)
    if hx(request) and cible(request) == "planning":
        return fragments([rendre("partials/planning.html", planning=vue, oob=True)])
    return page(request, "planning.html", {"titre": "Planning", "actif": "/", "planning": vue})


@router.get("/dashboard")
async def dashboard(request: Request):
    resume = await run_in_threadpool(charger_resume)
    return page(request, "dashboard.html", {"titre": "Dashboard", "actif": "/dashboard", "resume": resume})


@router.get("/clients")
async def clients(request: Request):
    lignes = await run_in_threadpool(lister_clients)
    return page(request, "clients.html", {"titre": "Clients", "actif": "/clients", "clients": lignes})


@router.post("/clients")
async def ajouter_client(request: Request):
    form = await request.form()
    nom = _texte(form, "nom")
    if not nom.strip():
        avertissement = toast("Le nom est obligatoire", "warning")
        if hx(request):
            return fragments([], avertissement)
        return rediriger(request, "/clients", avertissement)
    await run_in_threadpool(
        creer_client,
        nom,
        _texte(form, "email"),
        _texte(form, "telephone"),
        _texte(form, "adresse"),
        _texte(form, "notes"),
        _texte(form, "pays"),
    )
    lignes = await run_in_threadpool(lister_clients)
    confirme = toast("Client ajouté", "positive")
    if hx(request):
        reponse = fragments([rendre("partials/maj_clients.html", clients=lignes, oob=True)], confirme)
        reponse.headers["HX-Trigger"] = "client-ajoute"
        return reponse
    return rediriger(request, "/clients", confirme)


@router.get("/chambres")
async def chambres(request: Request):
    lignes = await run_in_threadpool(lister_chambres)
    return page(
        request,
        "chambres.html",
        {"titre": "Chambres", "actif": "/chambres", "chambres": lignes, "position": _prochaine_position(lignes)},
    )


@router.post("/chambres")
async def ajouter_chambre(request: Request):
    form = await request.form()
    nom = _texte(form, "nom")
    if not nom.strip():
        avertissement = toast("Le nom est obligatoire", "warning")
        if hx(request):
            return fragments([], avertissement)
        return rediriger(request, "/chambres", avertissement)
    position = entier(form.get("position"), 0) or 0
    try:
        await run_in_threadpool(creer_chambre, nom, position, _texte(form, "type_chambre"))
    except IntegrityError:
        erreur = toast("Ce nom de chambre existe déjà", "negative")
        if hx(request):
            return fragments([], erreur)
        return rediriger(request, "/chambres", erreur)
    lignes = await run_in_threadpool(lister_chambres)
    confirme = toast("Chambre ajoutée", "positive")
    if hx(request):
        return fragments(
            [
                rendre(
                    "partials/maj_chambres.html",
                    chambres=lignes,
                    position=_prochaine_position(lignes),
                    oob=True,
                )
            ],
            confirme,
        )
    return rediriger(request, "/chambres", confirme)


@router.post("/chambres/{chambre_id}/type")
async def type_chambre(request: Request, chambre_id: int):
    form = await request.form()
    valeur = _texte(form, "type_chambre").strip()
    avant = _texte(form, "avant").strip()
    if valeur == avant:
        return fragments([])
    await run_in_threadpool(modifier_type_chambre, chambre_id, valeur)
    return fragments(
        [rendre("partials/avant_type.html", chambre_id=chambre_id, valeur=valeur, oob=True)],
        toast(f"Type de la chambre {_texte(form, 'nom_chambre')} enregistré", "positive"),
    )


@router.post("/chambres/{chambre_id}/etat")
async def etat_chambre(request: Request, chambre_id: int, lundi: date | None = None):
    await run_in_threadpool(basculer_etat, chambre_id)
    visee = cible(request)
    if visee == "planning":
        aujourd_hui = date.today()
        debut = lundi_de(lundi or aujourd_hui)
        data = await run_in_threadpool(charger_planning, debut, debut + timedelta(days=7))
        vue = preparer_planning(debut, aujourd_hui, data)
        return fragments([rendre("partials/planning.html", planning=vue, oob=True)])
    if visee == "liste-chambres" or hx(request):
        lignes = await run_in_threadpool(lister_chambres)
        return fragments([rendre("partials/liste_chambres.html", chambres=lignes, oob=True)])
    return rediriger(request, "/chambres")


@router.get("/reservations")
async def reservations(request: Request):
    clients = await run_in_threadpool(options_clients)
    lignes = await run_in_threadpool(lister_reservations)
    return page(
        request,
        "reservations.html",
        {
            "titre": "Réservations",
            "actif": "/reservations",
            "clients": clients,
            "reservations": preparer_reservations(lignes),
        },
    )


@router.get("/reservations/nouvelle")
async def dialogue_reservation(request: Request):
    clients = await run_in_threadpool(options_clients)
    if not clients:
        return rediriger(request, "/clients", toast("Ajoutez d'abord un client", "warning"))
    return fragments([rendre("partials/dialogue_reservation.html", clients=clients, oob=True)])


@router.post("/reservations")
async def creer(request: Request):
    form = await request.form()
    client_id = entier(form.get("client_id"), None)
    if client_id is None:
        avertissement = toast("Choisissez un client", "warning")
        if hx(request):
            clients = await run_in_threadpool(options_clients)
            return fragments([rendre("partials/dialogue_reservation.html", clients=clients, oob=True)], avertissement)
        return rediriger(request, "/reservations", avertissement)
    reservation_id = await run_in_threadpool(creer_reservation, client_id)
    request.session["reservation_ouverte"] = reservation_id
    return rediriger(request, f"/reservations/{reservation_id}")


def _prochaine_position(chambres: list[dict]) -> int:
    return max((chambre["position"] for chambre in chambres), default=0) + 1
