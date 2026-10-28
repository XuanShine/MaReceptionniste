"""Dashboard, planning et listes."""

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from hotel_pms.lecture import lister_chambres, lister_clients, lister_produits, resumer_sejours
from hotel_pms.models import Chambre, Client, EtatChambre, Produit, Sejour
from hotel_pms.saisie import couper, parser_decimal
from hotel_pms.web import flash, ouvrir, rendre, verifier_csrf

router = APIRouter()


def _rediriger(chemin: str) -> RedirectResponse:
    return RedirectResponse(chemin, status_code=303)


@router.get("/")
def racine():
    return _rediriger("/dashboard")


@router.get("/dashboard")
def dashboard(request: Request):
    aujourdhui = date.today()
    with ouvrir(request) as session:
        resumes = resumer_sejours(session)
        en_cours = [resume for resume in resumes if resume.est_en_cours]
        return rendre(
            request,
            "dashboard.html",
            session=session,
            actif="dashboard",
            aujourdhui=aujourdhui,
            en_cours=en_cours,
            arrivees=[resume for resume in resumes if resume.debut == aujourdhui],
            departs=[resume for resume in resumes if resume.fin == aujourdhui],
            reste_total=sum((resume.reste for resume in en_cours), Decimal("0.00")),
            nb_chambres=len(lister_chambres(session)),
        )


@router.get("/planning")
def planning(request: Request, debut: str | None = None):
    if debut:
        try:
            origine = date.fromisoformat(debut)
        except ValueError:
            origine = date.today() - timedelta(days=1)
    else:
        origine = date.today() - timedelta(days=1)
    jours = [origine + timedelta(days=i) for i in range(14)]
    with ouvrir(request) as session:
        chambres = lister_chambres(session)
        sejours = list(session.exec(select(Sejour)).all())
        grille: dict[int, dict[date, tuple[int, str]]] = {}
        for sejour in sejours:
            for ligne in sejour.lignes:
                if ligne.chambre_id is None:
                    continue
                jour = ligne.date_debut
                while jour < ligne.date_fin:
                    grille.setdefault(ligne.chambre_id, {})[jour] = (sejour.id or 0, sejour.nom)
                    jour += timedelta(days=1)
        return rendre(
            request,
            "planning.html",
            session=session,
            actif="planning",
            chambres=chambres,
            jours=jours,
            grille=grille,
            aujourdhui=date.today(),
            precedent=origine - timedelta(days=7),
            suivant=origine + timedelta(days=7),
        )


@router.get("/sejours")
def liste_sejours(request: Request):
    with ouvrir(request) as session:
        return rendre(
            request,
            "sejours.html",
            session=session,
            actif="sejours",
            resumes=resumer_sejours(session),
        )


@router.get("/produits")
def produits(request: Request):
    with ouvrir(request) as session:
        return rendre(
            request,
            "produits.html",
            session=session,
            actif="produits",
            produits=lister_produits(session),
        )


@router.post("/produits")
def ajouter_produit(
    request: Request,
    csrf: str = Form(""),
    nom: str = Form(""),
    prix_ttc: str = Form(""),
    taux_tva: str = Form("10"),
):
    verifier_csrf(request, csrf)
    nom_propre = couper(nom, 120)
    if not nom_propre:
        flash(request, "Le nom du produit est obligatoire.")
        return _rediriger("/produits")
    try:
        prix = parser_decimal(prix_ttc, Decimal("0"), Decimal("1000000"))
        tva = parser_decimal(taux_tva or "0", Decimal("0"), Decimal("100"))
    except ValueError:
        flash(request, "Prix ou TVA invalide.")
        return _rediriger("/produits")
    with ouvrir(request) as session:
        session.add(Produit(nom=nom_propre, prix_ttc=prix, taux_tva=tva))
        session.commit()
    flash(request, "Produit ajouté.")
    return _rediriger("/produits")


@router.post("/produits/{produit_id}/supprimer")
def supprimer_produit(request: Request, produit_id: int, csrf: str = Form("")):
    verifier_csrf(request, csrf)
    with ouvrir(request) as session:
        produit = session.get(Produit, produit_id)
        if produit is None:
            flash(request, "Produit introuvable.")
        else:
            session.delete(produit)
            session.commit()
            flash(request, "Produit supprimé.")
    return _rediriger("/produits")


@router.get("/chambres")
def chambres(request: Request):
    with ouvrir(request) as session:
        return rendre(
            request,
            "chambres.html",
            session=session,
            actif="chambres",
            chambres=lister_chambres(session),
        )


@router.post("/chambres")
def ajouter_chambre(
    request: Request,
    csrf: str = Form(""),
    numero: str = Form(""),
    type_chambre: str = Form(""),
    etat: str = Form("non_pret"),
):
    verifier_csrf(request, csrf)
    numero_propre = couper(numero, 20)
    type_propre = couper(type_chambre, 40)
    if not numero_propre or not type_propre:
        flash(request, "Le numéro et le type sont obligatoires.")
        return _rediriger("/chambres")
    try:
        etat_enum = EtatChambre(etat)
    except ValueError:
        etat_enum = EtatChambre.non_pret
    with ouvrir(request) as session:
        session.add(Chambre(numero=numero_propre, type_chambre=type_propre, etat=etat_enum))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            flash(request, "Ce numéro de chambre existe déjà.")
            return _rediriger("/chambres")
    flash(request, "Chambre ajoutée.")
    return _rediriger("/chambres")


@router.post("/chambres/{chambre_id}/supprimer")
def supprimer_chambre(request: Request, chambre_id: int, csrf: str = Form("")):
    verifier_csrf(request, csrf)
    with ouvrir(request) as session:
        chambre = session.get(Chambre, chambre_id)
        if chambre is None:
            flash(request, "Chambre introuvable.")
        else:
            _supprimer(session, chambre, request, "Chambre supprimée.")
    return _rediriger("/chambres")


@router.get("/clients")
def clients(request: Request):
    with ouvrir(request) as session:
        return rendre(
            request,
            "clients.html",
            session=session,
            actif="clients",
            clients=lister_clients(session),
        )


@router.post("/clients")
def ajouter_client(
    request: Request,
    csrf: str = Form(""),
    nom: str = Form(""),
    telephone: str = Form(""),
    email: str = Form(""),
):
    verifier_csrf(request, csrf)
    nom_propre = couper(nom, 160)
    if not nom_propre:
        flash(request, "Le nom du client est obligatoire.")
        return _rediriger("/clients")
    with ouvrir(request) as session:
        session.add(Client(nom=nom_propre, telephone=couper(telephone, 40), email=couper(email, 160)))
        session.commit()
    flash(request, "Client ajouté.")
    return _rediriger("/clients")


@router.post("/clients/{client_id}/supprimer")
def supprimer_client(request: Request, client_id: int, csrf: str = Form("")):
    verifier_csrf(request, csrf)
    with ouvrir(request) as session:
        client = session.get(Client, client_id)
        if client is None:
            flash(request, "Client introuvable.")
        else:
            _supprimer(session, client, request, "Client supprimé.")
    return _rediriger("/clients")


@router.get("/parametres")
def parametres(request: Request):
    with ouvrir(request) as session:
        return rendre(
            request,
            "parametres.html",
            session=session,
            actif="parametres",
            db_path=request.app.state.db_path,
        )


def _supprimer(session: Session, objet, request: Request, succes: str) -> None:
    try:
        session.delete(objet)
        session.commit()
    except IntegrityError:
        session.rollback()
        flash(request, "Suppression impossible : l'élément est utilisé.")
        return
    flash(request, succes)
