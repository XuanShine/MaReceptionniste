"""Fiche séjour : en-tête, réservations, règlements."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from hotel_pms.compta import totaux_sejour
from hotel_pms.constants import BLOCS, MOYENS_PAIEMENT, ONGLETS
from hotel_pms.format import euro
from hotel_pms.lecture import lister_chambres, lister_clients, lister_produits
from hotel_pms.models import (
    Chambre,
    Client,
    LigneConsommation,
    LigneReservation,
    ModificationSejour,
    Produit,
    Reglement,
    Sejour,
    StatutSejour,
)
from hotel_pms.saisie import couper, parser_date, parser_decimal, parser_entier
from hotel_pms.web import est_htmx, flash, fragment, ouvrir, rendre, verifier_csrf

router = APIRouter()


@dataclass(frozen=True)
class SaisieReglement:
    date_reglement: str
    type_reglement: str
    montant: str


@dataclass(frozen=True)
class ReglementLu:
    date_reglement: date
    type_reglement: str
    montant: Decimal


@dataclass(frozen=True)
class EchecReglement:
    message: str
    saisie: SaisieReglement


def lire_reglement(saisie: SaisieReglement) -> ReglementLu | EchecReglement:
    try:
        jour = parser_date(saisie.date_reglement, obligatoire=True)
    except ValueError:
        return EchecReglement("Date invalide.", saisie)
    if jour is None:
        return EchecReglement("Date invalide.", saisie)
    if saisie.type_reglement not in MOYENS_PAIEMENT:
        return EchecReglement("Moyen de paiement inconnu.", saisie)
    try:
        montant = parser_decimal(saisie.montant, Decimal("0.01"), Decimal("1000000"))
    except ValueError:
        return EchecReglement("Montant invalide.", saisie)
    return ReglementLu(date_reglement=jour, type_reglement=saisie.type_reglement, montant=montant)


def _onglet(valeur: str | None) -> str:
    return valeur if valeur in ONGLETS else "reservations"


def _bloc(valeur: str | None) -> str:
    return valeur if valeur in BLOCS else "notes"


def _rediriger(chemin: str) -> RedirectResponse:
    return RedirectResponse(chemin, status_code=303)


def _maintenant() -> datetime:
    return datetime.now(UTC)


def _journal(session: Session, sejour_id: int, description: str) -> None:
    session.add(
        ModificationSejour(
            sejour_id=sejour_id,
            date_modif=_maintenant(),
            description=couper(description, 300),
        )
    )


def _contexte_fiche(session: Session, sejour: Sejour, **extra):
    return {
        "sejour": sejour,
        "totaux": totaux_sejour(list(sejour.lignes), list(sejour.reglements)),
        "chambres": lister_chambres(session),
        "produits": lister_produits(session),
        "clients": lister_clients(session),
        "aujourdhui": date.today(),
        "demain": date.today() + timedelta(days=1),
        **extra,
    }


def _fiche(
    request: Request,
    session: Session,
    sejour: Sejour,
    onglet: str,
    bloc: str,
    echec_reglement: EchecReglement | None = None,
):
    return rendre(
        request,
        "sejour.html",
        session=session,
        actif="detail",
        onglet=onglet,
        bloc=bloc,
        erreur_ligne=None,
        echec_reglement=echec_reglement,
        brouillon_ligne=None,
        brouillon_conso=None,
        **_contexte_fiche(session, sejour),
    )


@router.get("/sejours/{sejour_id}")
def voir_sejour(request: Request, sejour_id: int, onglet: str = "reservations", bloc: str = "notes"):
    with ouvrir(request) as session:
        sejour = session.get(Sejour, sejour_id)
        if sejour is None:
            flash(request, "Séjour introuvable.")
            return _rediriger("/sejours")
        request.session["sejour_id"] = sejour.id
        return _fiche(request, session, sejour, _onglet(onglet), _bloc(bloc))


@router.post("/sejours/{sejour_id}/statut")
def changer_statut(
    request: Request,
    sejour_id: int,
    csrf: str = Form(""),
    traite: str | None = Form(None),
):
    verifier_csrf(request, csrf)
    with ouvrir(request) as session:
        sejour = session.get(Sejour, sejour_id)
        if sejour is None:
            return _rediriger("/sejours")
        nouveau = StatutSejour.traite if traite == "1" else StatutSejour.en_cours
        if sejour.statut_enum != nouveau:
            sejour.statut = nouveau
            _journal(session, sejour.id, f"Statut : {sejour.statut_libelle}")
            session.add(sejour)
            session.commit()
            session.refresh(sejour)
        if est_htmx(request):
            return fragment(request, "partials/statut.html", sejour=sejour)
        return _rediriger(f"/sejours/{sejour.id}")


@router.post("/sejours/{sejour_id}/actions")
def actions(
    request: Request,
    sejour_id: int,
    csrf: str = Form(""),
    action: str = Form(""),
    nom: str = Form(""),
    client_id: str = Form(""),
    pays_nat: str = Form(""),
    partenaire: str = Form(""),
    type_voiture: str = Form(""),
    date_facture: str = Form(""),
    num_facture: str = Form(""),
    fact_client_uniquement: str | None = Form(None),
    telephone_fixe: str = Form(""),
    telephone_mobile: str = Form(""),
    fax: str = Form(""),
    email: str = Form(""),
    ref_partenaire: str = Form(""),
    ref_distributeur: str = Form(""),
    notes: str = Form(""),
    notes_internes: str = Form(""),
    notes_tempo: str = Form(""),
    facturation_client: str = Form(""),
):
    verifier_csrf(request, csrf)
    with ouvrir(request) as session:
        sejour = session.get(Sejour, sejour_id)
        if sejour is None:
            flash(request, "Séjour introuvable.")
            return _rediriger("/sejours")
        erreur = _appliquer(
            session,
            sejour,
            nom=nom,
            client_id=client_id,
            pays_nat=pays_nat,
            partenaire=partenaire,
            type_voiture=type_voiture,
            date_facture=date_facture,
            num_facture=num_facture,
            fact_client_uniquement=fact_client_uniquement == "1",
            telephone_fixe=telephone_fixe,
            telephone_mobile=telephone_mobile,
            fax=fax,
            email=email,
            ref_partenaire=ref_partenaire,
            ref_distributeur=ref_distributeur,
            notes=notes,
            notes_internes=notes_internes,
            notes_tempo=notes_tempo,
            facturation_client=facturation_client,
        )
        if erreur:
            flash(request, erreur)
            return _rediriger(f"/sejours/{sejour.id}")
        if action == "facturer":
            if sejour.num_facture:
                message = f"Facture {sejour.num_facture} déjà émise."
            else:
                sejour.date_facture = date.today()
                sejour.num_facture = _prochain_numero(session)
                _journal(session, sejour.id, f"Facture {sejour.num_facture}")
                message = f"Facture {sejour.num_facture} créée."
        elif action == "confirmer":
            _journal(session, sejour.id, "Séjour confirmé")
            message = "Séjour confirmé."
        elif action == "ok":
            message = "Séjour enregistré."
        else:
            flash(request, "Action inconnue.")
            return _rediriger(f"/sejours/{sejour.id}")
        session.add(sejour)
        session.commit()
        flash(request, message)
        if action == "ok":
            return _rediriger("/sejours")
        return _rediriger(f"/sejours/{sejour.id}")


@router.post("/sejours/{sejour_id}/abandon")
def abandonner(request: Request, sejour_id: int, csrf: str = Form("")):
    verifier_csrf(request, csrf)
    request.session.pop("sejour_id", None)
    flash(request, "Modifications abandonnées.")
    return _rediriger("/sejours")


@router.post("/sejours/{sejour_id}/reglements")
def ajouter_reglement(
    request: Request,
    sejour_id: int,
    csrf: str = Form(""),
    date_reglement: str = Form(""),
    type_reglement: str = Form(""),
    montant: str = Form(""),
):
    verifier_csrf(request, csrf)
    with ouvrir(request) as session:
        sejour = session.get(Sejour, sejour_id)
        if sejour is None:
            return _rediriger("/sejours")
        saisie = SaisieReglement(
            date_reglement=date_reglement,
            type_reglement=type_reglement,
            montant=montant,
        )
        resultat = lire_reglement(saisie)
        if isinstance(resultat, EchecReglement):
            if est_htmx(request):
                return _panneau_reglements(request, session, sejour, resultat)
            return _fiche(request, session, sejour, "reglements", "notes", echec_reglement=resultat)
        session.add(
            Reglement(
                sejour_id=sejour.id,
                date_reglement=resultat.date_reglement,
                type_reglement=resultat.type_reglement,
                montant=resultat.montant,
            )
        )
        _journal(
            session,
            sejour.id,
            f"Règlement {resultat.type_reglement} : {euro(resultat.montant)}",
        )
        session.commit()
        session.refresh(sejour)
        if est_htmx(request):
            return _panneau_reglements(request, session, sejour, None)
        flash(request, "Règlement enregistré.")
        return _rediriger(f"/sejours/{sejour.id}?onglet=reglements")


@router.post("/sejours/{sejour_id}/lignes")
def ajouter_ligne(
    request: Request,
    sejour_id: int,
    csrf: str = Form(""),
    type_chambre: str = Form(""),
    chambre_id: str = Form(""),
    date_debut: str = Form(""),
    date_fin: str = Form(""),
    prix_ttc: str = Form(""),
    remise_pct: str = Form("0"),
    adultes: str = Form("1"),
    enfants: str = Form("0"),
    taxe_sejour: str = Form("0"),
):
    verifier_csrf(request, csrf)
    with ouvrir(request) as session:
        sejour = session.get(Sejour, sejour_id)
        if sejour is None:
            return _rediriger("/sejours")
        erreur, ligne = _lire_ligne(
            session,
            type_chambre=type_chambre,
            chambre_id=chambre_id,
            date_debut=date_debut,
            date_fin=date_fin,
            prix_ttc=prix_ttc,
            remise_pct=remise_pct,
            adultes=adultes,
            enfants=enfants,
            taxe_sejour=taxe_sejour,
        )
        if erreur or ligne is None:
            brouillon = _brouillon_ligne(
                type_chambre=type_chambre,
                chambre_id=chambre_id,
                date_debut=date_debut,
                date_fin=date_fin,
                prix_ttc=prix_ttc,
                remise_pct=remise_pct,
                adultes=adultes,
                enfants=enfants,
                taxe_sejour=taxe_sejour,
            )
            if est_htmx(request):
                return _panneau_reservations(request, session, sejour, erreur or "Ligne invalide.", brouillon)
            flash(request, erreur or "Ligne invalide.")
            return _rediriger(f"/sejours/{sejour.id}?onglet=reservations")
        ligne.sejour_id = sejour.id
        session.add(ligne)
        chambre = session.get(Chambre, ligne.chambre_id) if ligne.chambre_id else None
        numero = chambre.numero if chambre else "—"
        _journal(
            session,
            sejour.id,
            f"Ligne {ligne.type_chambre} chambre {numero} du {ligne.date_debut:%d/%m/%Y} au {ligne.date_fin:%d/%m/%Y}",
        )
        session.commit()
        session.refresh(sejour)
        if est_htmx(request):
            return _panneau_reservations(request, session, sejour, None)
        flash(request, "Ligne ajoutée.")
        return _rediriger(f"/sejours/{sejour.id}?onglet=reservations")


@router.post("/sejours/{sejour_id}/consommations")
def ajouter_consommation(
    request: Request,
    sejour_id: int,
    csrf: str = Form(""),
    produit_id: str = Form(""),
    prix_unitaire: str = Form(""),
    quantite: str = Form("1"),
):
    verifier_csrf(request, csrf)
    with ouvrir(request) as session:
        sejour = session.get(Sejour, sejour_id)
        if sejour is None:
            return _rediriger("/sejours")
        erreur, ligne = _lire_conso(
            session,
            produit_id=produit_id,
            prix_unitaire=prix_unitaire,
            quantite=quantite,
        )
        if erreur or ligne is None:
            brouillon = _brouillon_conso(produit_id=produit_id, prix_unitaire=prix_unitaire, quantite=quantite)
            if est_htmx(request):
                return _panneau_consommations(request, session, sejour, erreur or "Ligne invalide.", brouillon)
            flash(request, erreur or "Ligne invalide.")
            return _rediriger(f"/sejours/{sejour.id}?onglet=consommations")
        ligne.sejour_id = sejour.id
        session.add(ligne)
        _journal(session, sejour.id, f"Consommation {ligne.nom} × {ligne.quantite} : {euro(ligne.prix_total)}")
        session.commit()
        session.refresh(sejour)
        if est_htmx(request):
            return _panneau_consommations(request, session, sejour, None)
        flash(request, "Consommation enregistrée.")
        return _rediriger(f"/sejours/{sejour.id}?onglet=consommations")


def _panneau_reservations(
    request: Request,
    session: Session,
    sejour: Sejour,
    erreur: str | None,
    brouillon: dict | None = None,
):
    return fragment(
        request,
        "partials/panneau_reservations.html",
        erreur_ligne=erreur,
        brouillon_ligne=brouillon,
        **_contexte_fiche(session, sejour, oob=True, onglet="reservations"),
    )


def _panneau_reglements(
    request: Request,
    session: Session,
    sejour: Sejour,
    echec: EchecReglement | None,
):
    return fragment(
        request,
        "partials/panneau_reglements.html",
        echec_reglement=echec,
        **_contexte_fiche(session, sejour, oob=True, onglet="reglements"),
    )


def _appliquer(session: Session, sejour: Sejour, **champs) -> str | None:
    nom = couper(champs["nom"], 160)
    if not nom:
        return "Le nom est obligatoire."
    try:
        client_pk = int(champs["client_id"])
    except ValueError:
        return "Client introuvable."
    client = session.get(Client, client_pk)
    if client is None:
        return "Client introuvable."
    try:
        facture = parser_date(champs["date_facture"])
    except ValueError:
        return "Date de facture invalide."
    sejour.nom = nom
    sejour.client_id = client.id
    sejour.pays_nat = couper(champs["pays_nat"], 80)
    sejour.partenaire = couper(champs["partenaire"], 80)
    sejour.type_voiture = couper(champs["type_voiture"], 40)
    sejour.date_facture = facture
    sejour.num_facture = couper(champs["num_facture"], 40) or None
    sejour.fact_client_uniquement = bool(champs["fact_client_uniquement"])
    sejour.telephone_fixe = couper(champs["telephone_fixe"], 40)
    sejour.telephone_mobile = couper(champs["telephone_mobile"], 40)
    sejour.fax = couper(champs["fax"], 40)
    sejour.email = couper(champs["email"], 160)
    sejour.ref_partenaire = couper(champs["ref_partenaire"], 80)
    sejour.ref_distributeur = couper(champs["ref_distributeur"], 80)
    sejour.notes = couper(champs["notes"], 4000)
    sejour.notes_internes = couper(champs["notes_internes"], 4000)
    sejour.notes_tempo = couper(champs["notes_tempo"], 4000)
    sejour.facturation_client = couper(champs["facturation_client"], 4000)
    return None


def _prochain_numero(session: Session) -> str:
    annee = date.today().year
    prefixe = f"F-{annee}-"
    suivant = 1
    for numero in session.exec(select(Sejour.num_facture)).all():
        texte = numero[0] if isinstance(numero, tuple) else numero
        if not texte or not str(texte).startswith(prefixe):
            continue
        try:
            suivant = max(suivant, int(str(texte).removeprefix(prefixe)) + 1)
        except ValueError:
            continue
    return f"{prefixe}{suivant:04d}"


def _panneau_consommations(
    request: Request,
    session: Session,
    sejour: Sejour,
    erreur: str | None,
    brouillon: dict | None = None,
):
    return fragment(
        request,
        "partials/panneau_consommations.html",
        erreur_conso=erreur,
        brouillon_conso=brouillon,
        **_contexte_fiche(session, sejour, oob=False, onglet="consommations"),
    )


def _brouillon_conso(**champs) -> dict[str, str]:
    return {
        "produit_id": champs["produit_id"],
        "prix_unitaire": champs["prix_unitaire"],
        "quantite": champs["quantite"] or "1",
    }


def _lire_conso(session: Session, **champs) -> tuple[str | None, LigneConsommation | None]:
    try:
        produit_pk = int(champs["produit_id"])
    except ValueError:
        return "Choisissez un produit.", None
    produit = session.get(Produit, produit_pk)
    if produit is None:
        return "Produit introuvable.", None
    try:
        prix = parser_decimal(champs["prix_unitaire"] or str(produit.prix_ttc), Decimal("0"), Decimal("100000"))
    except ValueError:
        return "Prix unitaire invalide.", None
    try:
        quantite = parser_entier(champs["quantite"] or "1", 1, 999)
    except ValueError:
        return "Quantité invalide.", None
    return None, LigneConsommation(
        sejour_id=0,
        produit_id=produit.id,
        nom=produit.nom,
        prix_unitaire=prix,
        quantite=quantite,
    )


def _brouillon_ligne(**champs) -> dict[str, str]:
    nuits = ""
    try:
        debut = date.fromisoformat(champs["date_debut"])
        fin = date.fromisoformat(champs["date_fin"])
    except ValueError:
        debut = fin = None
    if debut is not None and fin is not None and fin > debut:
        nuits = str((fin - debut).days)
    return {
        "type_chambre": champs["type_chambre"],
        "chambre_id": champs["chambre_id"],
        "date_debut": champs["date_debut"],
        "date_fin": champs["date_fin"],
        "prix_ttc": champs["prix_ttc"],
        "remise_pct": champs["remise_pct"],
        "adultes": champs["adultes"],
        "enfants": champs["enfants"],
        "taxe_sejour": champs["taxe_sejour"],
        "nuits": nuits,
    }


def _lire_ligne(session: Session, **champs) -> tuple[str | None, LigneReservation | None]:
    try:
        debut = parser_date(champs["date_debut"], obligatoire=True)
        fin = parser_date(champs["date_fin"], obligatoire=True)
        prix = parser_decimal(champs["prix_ttc"], Decimal("0"), Decimal("1000000"))
        remise = parser_decimal(champs["remise_pct"] or "0", Decimal("0"), Decimal("100"))
        taxe = parser_decimal(champs["taxe_sejour"] or "0", Decimal("0"), Decimal("100000"))
        adultes = parser_entier(champs["adultes"] or "1", 0, 20)
        enfants = parser_entier(champs["enfants"] or "0", 0, 20)
        chambre_pk = int(champs["chambre_id"])
    except (ValueError, TypeError):
        return "Vérifiez les dates, le prix et la chambre.", None
    if debut is None or fin is None or fin <= debut:
        return "La date de fin doit être après le début.", None
    nuits = (fin - debut).days
    if nuits > 60:
        return "60 nuits maximum.", None
    chambre = session.get(Chambre, chambre_pk)
    if chambre is None:
        return "Chambre introuvable.", None
    type_chambre = couper(champs["type_chambre"], 40) or chambre.type_chambre
    return None, LigneReservation(
        sejour_id=0,
        chambre_id=chambre.id,
        type_chambre=type_chambre,
        nb_jours=nuits,
        date_debut=debut,
        date_fin=fin,
        prix_ttc=prix,
        remise_pct=remise,
        adultes=adultes,
        enfants=enfants,
        taxe_sejour=taxe,
    )
