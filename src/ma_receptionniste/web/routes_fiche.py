from datetime import date, timedelta

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from ma_receptionniste.consultations import fiche_sejour, lister_chambres
from ma_receptionniste.models import ModeReglement
from ma_receptionniste.saisie import (
    FacturationImpossible,
    FicheInvalide,
    ajouter_consommation,
    ajouter_note,
    ajouter_reglement,
    ajouter_sejour,
    annuler_reservation,
    champs_modifies,
    enregistrer_fiche,
    facturer,
    modifier_sejour,
    supprimer_sejour,
)
from ma_receptionniste.sejours import ChambreOccupee, SejourInvalide
from ma_receptionniste.web.formes import entier, lire_date, montant, texte_champs, valeurs_enregistrees, valeurs_fiche
from ma_receptionniste.web.rendu import fragments, hx, identifiant, page, rediriger, rendre
from ma_receptionniste.web.rendu import message as toast
from ma_receptionniste.web.vue import bornes_brouillon, calculer_apercu, contexte_fiche

router = APIRouter()

MAJ = (
    "partials/entete_fiche.html",
    "partials/lecture.html",
    "partials/compteurs.html",
    "partials/actions.html",
    "partials/totaux.html",
    "partials/montant.html",
    "partials/historique.html",
)


async def _charger(reservation_id: int) -> dict | None:
    return await run_in_threadpool(fiche_sejour, reservation_id)


def _retenir(request: Request, reservation_id: int | None) -> None:
    if reservation_id is None:
        request.session.pop("reservation_ouverte", None)
    else:
        request.session["reservation_ouverte"] = reservation_id


def _morceaux(fiche: dict, *noms: str, **extra) -> list[str]:
    contexte = contexte_fiche(fiche, oob=True, **extra)
    return [rendre(nom, **contexte) for nom in noms]


def _page_fiche(request: Request, fiche: dict, valeurs: dict, erreur: str | None = None):
    return page(
        request,
        "fiche.html",
        {
            "titre": "Fiche séjour",
            "actif": "detail",
            "valeurs": texte_champs(valeurs),
            "erreur": erreur,
            **contexte_fiche(fiche),
        },
    )


@router.get("/reservations/{reservation_id}")
async def voir(request: Request, reservation_id: int):
    fiche = await _charger(reservation_id)
    if fiche is None:
        _retenir(request, None)
        return page(
            request,
            "fiche_absente.html",
            {"titre": "Fiche séjour", "actif": "/reservations", "reservation_id": reservation_id},
        )
    _retenir(request, reservation_id)
    return _page_fiche(request, fiche, valeurs_enregistrees(fiche))


@router.post("/reservations/{reservation_id}")
async def enregistrer(request: Request, reservation_id: int):
    form = await request.form()
    valeurs = valeurs_fiche(form)
    try:
        libelles = await run_in_threadpool(enregistrer_fiche, reservation_id, identifiant(request), valeurs)
    except FicheInvalide as erreur:
        fiche = await _charger(reservation_id)
        if fiche is None:
            return rediriger(request, "/reservations")
        if hx(request):
            return fragments([], toast(str(erreur), "warning"))
        return _page_fiche(request, fiche, valeurs, str(erreur))
    if form.get("ensuite") == "planning":
        _retenir(request, None)
        return rediriger(request, "/")
    fiche = await _charger(reservation_id)
    if fiche is None:
        return rediriger(request, "/reservations")
    texte = "Fiche enregistrée" if libelles else "Aucune modification à enregistrer"
    type_ = "positive" if libelles else "info"
    if hx(request):
        return fragments(_morceaux(fiche, *MAJ), toast(texte, type_))
    return rediriger(request, f"/reservations/{reservation_id}", toast(texte, type_))


@router.post("/reservations/{reservation_id}/abandon")
async def abandonner(request: Request, reservation_id: int):
    form = await request.form()
    fiche = await _charger(reservation_id)
    if fiche is None:
        _retenir(request, None)
        return rediriger(request, "/reservations")
    if champs_modifies(valeurs_enregistrees(fiche), valeurs_fiche(form)):
        return fragments([rendre("partials/dialogue_abandon.html", fiche=fiche, oob=True)])
    _retenir(request, None)
    return rediriger(request, "/")


@router.post("/reservations/{reservation_id}/quitter")
async def quitter(request: Request, reservation_id: int):
    _retenir(request, None)
    return rediriger(request, "/")


@router.post("/reservations/{reservation_id}/facturer")
async def emettre_facture(request: Request, reservation_id: int):
    fiche = await _charger(reservation_id)
    if fiche is None:
        return rediriger(request, "/reservations")
    deja = fiche["reservation"]["numero_facture"] is not None
    try:
        numero = await run_in_threadpool(facturer, reservation_id, identifiant(request))
    except FacturationImpossible as erreur:
        return await _reste(request, reservation_id, toast(str(erreur), "warning"))
    fiche = await _charger(reservation_id)
    texte = f"La facture n° {numero} a déjà été émise" if deja else f"Facture n° {numero} émise"
    return await _reste(request, reservation_id, toast(texte, "info" if deja else "positive"), fiche)


@router.post("/reservations/{reservation_id}/annuler")
async def annuler(request: Request, reservation_id: int):
    await run_in_threadpool(annuler_reservation, reservation_id, identifiant(request))
    return await _reste(request, reservation_id, toast("Réservation annulée", "warning"), fermer_annulation=True)


@router.get("/reservations/{reservation_id}/lignes/nouvelle")
async def nouvelle_ligne(request: Request, reservation_id: int):
    fiche = await _charger(reservation_id)
    if fiche is None:
        return rediriger(request, "/reservations")
    chambres = await run_in_threadpool(lister_chambres)
    if not chambres:
        return fragments([], toast("Ajoutez d'abord une chambre", "warning"))
    debut, fin = bornes_brouillon(fiche)
    apercu = calculer_apercu(chambres, None, debut, fin, 1, 0, 0)
    contexte = contexte_fiche(fiche, oob=True, chambres=chambres, debut=debut, fin=fin, apercu=apercu, brouillon=True)
    return fragments(
        [
            rendre("partials/tbody_persist.html", **contexte),
            rendre("partials/tbody_brouillon.html", **contexte),
            rendre("partials/tbody_pied.html", **contexte),
        ]
    )


@router.get("/reservations/{reservation_id}/lignes/annuler")
async def annuler_brouillon(request: Request, reservation_id: int):
    fiche = await _charger(reservation_id)
    if fiche is None:
        return rediriger(request, "/reservations")
    contexte = contexte_fiche(fiche, oob=True, brouillon=False)
    return fragments(
        [
            rendre("partials/tbody_persist.html", **contexte),
            rendre("partials/tbody_brouillon.html", **contexte),
            rendre("partials/tbody_pied.html", **contexte),
        ]
    )


@router.get("/reservations/{reservation_id}/lignes/apercu")
async def apercu_ligne(request: Request, reservation_id: int):
    chambres = await run_in_threadpool(lister_chambres)
    debut = lire_date(request.query_params.get("date_debut"))
    fin = lire_date(request.query_params.get("date_fin"))
    ajuste = False
    if debut and (fin is None or fin <= debut):
        fin = debut + timedelta(days=1)
        ajuste = True
    apercu = calculer_apercu(
        chambres,
        entier(request.query_params.get("chambre_id"), None),
        debut,
        fin,
        entier(request.query_params.get("adultes"), 0) or 0,
        montant(request.query_params.get("prix")),
        entier(request.query_params.get("remise"), 0) or 0,
    )
    cible = request.query_params.get("cible")
    nom = "partials/apercu_dialogue.html" if cible == "dialogue" else "partials/apercu.html"
    return fragments(
        [
            rendre(
                nom,
                apercu=apercu,
                fiche={"id": reservation_id},
                fin=fin,
                ajuste=ajuste,
                oob=True,
            )
        ]
    )


@router.post("/reservations/{reservation_id}/lignes")
async def creer_ligne(request: Request, reservation_id: int):
    form = await request.form()
    chambre_id = entier(form.get("chambre_id"), None)
    debut = lire_date(form.get("date_debut"))
    fin = lire_date(form.get("date_fin"))
    if chambre_id is None or debut is None or fin is None:
        return await _echec_ligne(
            request, reservation_id, "Choisissez la chambre et les dates d'arrivée et de départ", "warning"
        )

    def ecrire() -> None:
        ajouter_sejour(
            reservation_id,
            chambre_id,
            debut,
            fin,
            str(form.get("nom_client") or ""),
            entier(form.get("adultes"), 0) or 0,
            entier(form.get("enfants"), 0) or 0,
            montant(form.get("prix")),
            entier(form.get("remise"), 0) or 0,
            identifiant(request),
        )

    try:
        await run_in_threadpool(ecrire)
    except ChambreOccupee as erreur:
        return await _echec_ligne(request, reservation_id, str(erreur), "negative")
    except SejourInvalide as erreur:
        return await _echec_ligne(request, reservation_id, str(erreur), "warning")
    return await _reste(
        request,
        reservation_id,
        toast("Ligne ajoutée", "positive"),
        lignes=True,
    )


@router.get("/reservations/{reservation_id}/lignes/{sejour_id}")
async def ouvrir_ligne(request: Request, reservation_id: int, sejour_id: int):
    fiche = await _charger(reservation_id)
    if fiche is None:
        return rediriger(request, "/reservations")
    ligne = next((item for item in fiche["lignes"] if item["id"] == sejour_id), None)
    if ligne is None:
        return fragments([], toast("Séjour introuvable", "warning"))
    chambres = await run_in_threadpool(lister_chambres)
    if not chambres:
        return fragments([], toast("Ajoutez d'abord une chambre", "warning"))
    apercu = calculer_apercu(
        chambres,
        ligne["chambre_id"],
        ligne["date_debut"],
        ligne["date_fin"],
        ligne["adultes"],
        ligne["prix_nuit_centimes"],
        ligne["remise_pct"],
    )
    return fragments(
        [
            rendre(
                "partials/dialogue_ligne.html",
                fiche=fiche,
                ligne=ligne,
                chambres=chambres,
                apercu=apercu,
                confirmer=False,
                oob=True,
            )
        ]
    )


@router.post("/reservations/{reservation_id}/lignes/{sejour_id}")
async def modifier_ligne(request: Request, reservation_id: int, sejour_id: int):
    form = await request.form()
    if form.get("action") == "supprimer":
        if form.get("confirmer") != "1":
            return await _dialogue_depuis_form(request, reservation_id, sejour_id, form, confirmer=True)
        await run_in_threadpool(supprimer_sejour, sejour_id, identifiant(request))
        return await _reste(request, reservation_id, toast("Ligne supprimée", "positive"), lignes=True, fermer=True)
    chambre_id = entier(form.get("chambre_id"), None)
    debut = lire_date(form.get("date_debut"))
    fin = lire_date(form.get("date_fin"))
    if chambre_id is None or debut is None or fin is None:
        return await _dialogue_depuis_form(
            request,
            reservation_id,
            sejour_id,
            form,
            confirmer=False,
            erreur="Choisissez la chambre et les dates d'arrivée et de départ",
        )

    def ecrire() -> None:
        modifier_sejour(
            sejour_id,
            chambre_id,
            debut,
            fin,
            entier(form.get("adultes"), 0) or 0,
            entier(form.get("enfants"), 0) or 0,
            montant(form.get("prix")),
            entier(form.get("remise"), 0) or 0,
            str(form.get("nom_client") or ""),
            identifiant(request),
        )

    try:
        await run_in_threadpool(ecrire)
    except ChambreOccupee as erreur:
        return await _dialogue_depuis_form(
            request, reservation_id, sejour_id, form, confirmer=False, erreur=str(erreur)
        )
    except SejourInvalide as erreur:
        return await _dialogue_depuis_form(
            request, reservation_id, sejour_id, form, confirmer=False, erreur=str(erreur)
        )
    return await _reste(request, reservation_id, toast("Ligne modifiée", "positive"), lignes=True, fermer=True)


@router.post("/reservations/{reservation_id}/consommations")
async def consommation(request: Request, reservation_id: int):
    form = await request.form()
    libelle = str(form.get("libelle") or "")
    if not libelle.strip() or str(form.get("prix_unitaire") or "").strip() == "":
        return await _reste(request, reservation_id, toast("Indiquez le libellé et le prix unitaire", "warning"))
    await run_in_threadpool(
        ajouter_consommation,
        reservation_id,
        libelle,
        entier(form.get("quantite"), 1) or 1,
        montant(form.get("prix_unitaire")),
        identifiant(request),
    )
    return await _reste(
        request,
        reservation_id,
        toast("Consommation ajoutée", "positive"),
        consommations=True,
        vider="form-consommation",
    )


@router.post("/reservations/{reservation_id}/reglements")
async def reglement(request: Request, reservation_id: int):
    form = await request.form()
    valeur = montant(form.get("montant"))
    if valeur <= 0:
        return await _reste(request, reservation_id, toast("Indiquez un montant", "warning"))
    try:
        mode = ModeReglement(str(form.get("mode") or ""))
    except ValueError:
        return await _reste(request, reservation_id, toast("Indiquez un montant", "warning"))
    await run_in_threadpool(ajouter_reglement, reservation_id, mode, valeur, identifiant(request))
    return await _reste(request, reservation_id, toast("Règlement enregistré", "positive"), reglements=True)


@router.post("/reservations/{reservation_id}/notes")
async def note(request: Request, reservation_id: int):
    form = await request.form()
    description = str(form.get("description") or "")
    if not description.strip():
        return await _reste(request, reservation_id, toast("La note est vide", "warning"))
    await run_in_threadpool(ajouter_note, reservation_id, identifiant(request), description)
    return await _reste(request, reservation_id, toast("Note ajoutée au journal", "positive"), vider="form-note")


async def _reste(
    request: Request,
    reservation_id: int,
    message: dict,
    fiche: dict | None = None,
    *,
    lignes: bool = False,
    consommations: bool = False,
    reglements: bool = False,
    fermer: bool = False,
    fermer_annulation: bool = False,
    vider: str | None = None,
):
    if fiche is None:
        fiche = await _charger(reservation_id)
    if fiche is None:
        return rediriger(request, "/reservations")
    if not hx(request):
        return rediriger(request, f"/reservations/{reservation_id}", message)
    noms = list(MAJ)
    if lignes:
        noms.extend(("partials/tbody_persist.html", "partials/tbody_brouillon.html", "partials/tbody_pied.html"))
    if consommations:
        noms.append("partials/consommations.html")
    if reglements:
        noms.append("partials/reglements.html")
    morceaux = _morceaux(fiche, *noms, brouillon=False)
    if fermer:
        morceaux.append(rendre("partials/dialogue_vide.html", oob=True))
    if fermer_annulation:
        morceaux.append(rendre("partials/dialogue_annulation.html", fiche=fiche, oob=True))
    if vider == "form-consommation":
        morceaux.append(rendre("partials/form_consommation.html", fiche=fiche, oob=True))
    elif vider == "form-note":
        morceaux.append(rendre("partials/form_note.html", fiche=fiche, oob=True))
    return fragments(morceaux, message)


async def _echec_ligne(request: Request, reservation_id: int, texte: str, type_: str):
    if hx(request):
        return fragments([], toast(texte, type_))
    return rediriger(request, f"/reservations/{reservation_id}", toast(texte, type_))


async def _dialogue_depuis_form(
    request, reservation_id, sejour_id, form, *, confirmer: bool, erreur: str | None = None
):
    fiche = await _charger(reservation_id)
    chambres = await run_in_threadpool(lister_chambres)
    debut = lire_date(form.get("date_debut"))
    fin = lire_date(form.get("date_fin"))
    ligne = {
        "id": sejour_id,
        "chambre_id": entier(form.get("chambre_id"), None),
        "chambre_nom": "",
        "date_debut": debut or date.today(),
        "date_fin": fin or date.today(),
        "adultes": entier(form.get("adultes"), 0) or 0,
        "enfants": entier(form.get("enfants"), 0) or 0,
        "prix_nuit_centimes": montant(form.get("prix")),
        "remise_pct": entier(form.get("remise"), 0) or 0,
        "nom_client": str(form.get("nom_client") or ""),
    }
    for chambre in chambres:
        if chambre["id"] == ligne["chambre_id"]:
            ligne["chambre_nom"] = chambre["nom"]
    apercu = calculer_apercu(
        chambres,
        ligne["chambre_id"],
        debut,
        fin,
        ligne["adultes"],
        ligne["prix_nuit_centimes"],
        ligne["remise_pct"],
    )
    corps = [
        rendre(
            "partials/dialogue_ligne.html",
            fiche=fiche or {"id": reservation_id},
            ligne=ligne,
            chambres=chambres,
            apercu=apercu,
            confirmer=confirmer,
            oob=True,
        )
    ]
    return fragments(corps, toast(erreur, "warning") if erreur else None)
