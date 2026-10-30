from datetime import date, timedelta

from fastapi import APIRouter, Request
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from ma_receptionniste.consultations import (
    charger_planning,
    charger_resume,
    lister_chambres,
    lister_clients,
    lister_occupations_chambres,
    lister_reservations,
    lister_types_chambres,
    options_clients,
)
from ma_receptionniste.facturation import TAXE_SEJOUR_CENTIMES
from ma_receptionniste.saisie import (
    CatalogueInvalide,
    attribuer_occupation_chambre,
    attribuer_type_chambre,
    basculer_etat,
    creer_chambre,
    creer_client,
    creer_occupation_chambre,
    creer_reservation,
    creer_type_chambre,
    modifier_occupation_chambre,
    renommer_type_chambre,
    supprimer_occupation_chambre,
    supprimer_type_chambre,
)
from ma_receptionniste.web.formes import entier
from ma_receptionniste.web.rendu import cible, fragments, hx, page, rediriger, rendre
from ma_receptionniste.web.rendu import message as toast
from ma_receptionniste.web.vue import lundi_de, preparer_planning, preparer_reservations

router = APIRouter()


_AVERTISSEMENTS = {
    "Le libellé est obligatoire",
    "Le nombre de personnes doit être au moins 1",
    "Le type de lits est obligatoire",
}


def _texte(form, cle: str) -> str:
    return str(form.get(cle) or "")


def _id_option(form, champ: str, introuvable: str) -> int | None:
    brut = str(form.get(champ) or "").strip()
    if not brut:
        return None
    try:
        return int(brut)
    except ValueError:
        raise CatalogueInvalide(introuvable) from None


def _nombre_personnes(form) -> int:
    try:
        return int(str(form.get("nombre_personnes") or "").strip())
    except ValueError:
        raise CatalogueInvalide("Le nombre de personnes doit être au moins 1") from None


def _ecran_chambres() -> dict:
    chambres = lister_chambres()
    return {
        "types": lister_types_chambres(),
        "occupations": lister_occupations_chambres(),
        "chambres": chambres,
        "position": _prochaine_position(chambres),
    }


def _ton(message: str) -> str:
    return "warning" if message in _AVERTISSEMENTS else "negative"


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
    return rediriger(request, "/parametres")


@router.post("/chambres")
async def ajouter_chambre(request: Request):
    form = await request.form()
    nom = _texte(form, "nom")
    if not nom.strip():
        avertissement = toast("Le nom est obligatoire", "warning")
        if hx(request):
            return fragments([], avertissement)
        return rediriger(request, "/parametres", avertissement)
    position = entier(form.get("position"), 0) or 0
    try:
        type_chambre_id = _id_option(form, "type_chambre_id", "Ce type est introuvable")
        occupation_chambre_id = _id_option(form, "occupation_chambre_id", "Cette occupation est introuvable")
        await run_in_threadpool(
            creer_chambre,
            nom,
            position,
            type_chambre_id=type_chambre_id,
            occupation_chambre_id=occupation_chambre_id,
        )
    except CatalogueInvalide as erreur:
        return await _echec(request, str(erreur))
    except IntegrityError:
        erreur = toast("Ce nom de chambre existe déjà", "negative")
        if hx(request):
            return fragments([], erreur)
        return rediriger(request, "/parametres", erreur)
    return await _succes(request, "Chambre ajoutée")


@router.post("/types-chambres")
async def ajouter_type(request: Request):
    form = await request.form()
    try:
        await run_in_threadpool(creer_type_chambre, _texte(form, "libelle"))
    except CatalogueInvalide as erreur:
        return await _echec(request, str(erreur))
    return await _succes(request, "Type ajouté")


@router.post("/types-chambres/{type_chambre_id}")
async def enregistrer_type(request: Request, type_chambre_id: int):
    form = await request.form()
    try:
        modifie = await run_in_threadpool(renommer_type_chambre, type_chambre_id, _texte(form, "libelle"))
    except CatalogueInvalide as erreur:
        return await _echec(request, str(erreur))
    if not modifie:
        return await _inchange(request)
    return await _succes(request, "Type enregistré")


@router.post("/types-chambres/{type_chambre_id}/supprimer")
async def retirer_type(request: Request, type_chambre_id: int):
    try:
        await run_in_threadpool(supprimer_type_chambre, type_chambre_id)
    except CatalogueInvalide as erreur:
        return await _echec(request, str(erreur))
    return await _succes(request, None)


@router.post("/occupations-chambres")
async def ajouter_occupation(request: Request):
    form = await request.form()
    try:
        await run_in_threadpool(creer_occupation_chambre, _nombre_personnes(form), _texte(form, "type_lits"))
    except CatalogueInvalide as erreur:
        return await _echec(request, str(erreur))
    return await _succes(request, "Occupation ajoutée")


@router.post("/occupations-chambres/{occupation_chambre_id}")
async def enregistrer_occupation(request: Request, occupation_chambre_id: int):
    form = await request.form()
    try:
        modifie = await run_in_threadpool(
            modifier_occupation_chambre,
            occupation_chambre_id,
            _nombre_personnes(form),
            _texte(form, "type_lits"),
        )
    except CatalogueInvalide as erreur:
        return await _echec(request, str(erreur))
    if not modifie:
        return await _inchange(request)
    return await _succes(request, "Occupation enregistrée")


@router.post("/occupations-chambres/{occupation_chambre_id}/supprimer")
async def retirer_occupation(request: Request, occupation_chambre_id: int):
    try:
        await run_in_threadpool(supprimer_occupation_chambre, occupation_chambre_id)
    except CatalogueInvalide as erreur:
        return await _echec(request, str(erreur))
    return await _succes(request, None)


@router.post("/chambres/{chambre_id}/type")
async def type_chambre(request: Request, chambre_id: int):
    form = await request.form()
    try:
        type_chambre_id = _id_option(form, "type_chambre_id", "Ce type est introuvable")
        change = await run_in_threadpool(attribuer_type_chambre, chambre_id, type_chambre_id)
    except CatalogueInvalide as erreur:
        return await _echec_liste(request, str(erreur))
    if not change:
        return await _inchange(request)
    return await _succes_liste(request, "Type enregistré")


@router.post("/chambres/{chambre_id}/occupation")
async def occupation_chambre(request: Request, chambre_id: int):
    form = await request.form()
    try:
        occupation_chambre_id = _id_option(form, "occupation_chambre_id", "Cette occupation est introuvable")
        change = await run_in_threadpool(attribuer_occupation_chambre, chambre_id, occupation_chambre_id)
    except CatalogueInvalide as erreur:
        return await _echec_liste(request, str(erreur))
    if not change:
        return await _inchange(request)
    return await _succes_liste(request, "Occupation enregistrée")


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
        return fragments([await _liste()])
    return rediriger(request, "/parametres")


@router.get("/parametres")
async def parametres(request: Request):
    return page(
        request,
        "parametres.html",
        {
            "titre": "Paramètres",
            "actif": "/parametres",
            "taxe_centimes": TAXE_SEJOUR_CENTIMES,
            **await run_in_threadpool(_ecran_chambres),
        },
    )


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


async def _inchange(request: Request):
    if hx(request):
        return fragments([])
    return rediriger(request, "/parametres")


async def _succes(request: Request, texte: str | None):
    message = toast(texte, "positive") if texte else None
    if hx(request):
        return fragments([await _maj()], message)
    return rediriger(request, "/parametres", message)


async def _echec(request: Request, message: str):
    avertissement = toast(message, _ton(message))
    if hx(request):
        return fragments([await _maj()], avertissement)
    return rediriger(request, "/parametres", avertissement)


async def _succes_liste(request: Request, texte: str):
    message = toast(texte, "positive")
    if hx(request):
        return fragments([await _liste()], message)
    return rediriger(request, "/parametres", message)


async def _echec_liste(request: Request, message: str):
    avertissement = toast(message, _ton(message))
    if hx(request):
        return fragments([await _liste()], avertissement)
    return rediriger(request, "/parametres", avertissement)


async def _maj() -> str:
    return rendre("partials/maj_parametres.html", **await run_in_threadpool(_ecran_chambres), oob=True)


async def _liste() -> str:
    ecran = await run_in_threadpool(_ecran_chambres)
    return rendre(
        "partials/liste_chambres.html",
        chambres=ecran["chambres"],
        types=ecran["types"],
        occupations=ecran["occupations"],
        oob=True,
    )
