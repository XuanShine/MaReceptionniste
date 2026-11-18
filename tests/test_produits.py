"""Catalogue de produits et vente sur une réservation."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

import ma_receptionniste.saisie as saisie
from ma_receptionniste.consultations import fiche_sejour, lister_produits
from ma_receptionniste.db import ajouter_colonnes_manquantes, create_db_and_tables
from ma_receptionniste.facturation import format_euros
from ma_receptionniste.models import Consommation, Produit, User
from ma_receptionniste.saisie import (
    ProduitInvalide,
    ajouter_consommation,
    ajouter_consommation_produit,
    creer_produit,
    creer_reservation,
    definir_produit_actif,
    modifier_consommation,
    modifier_produit,
)


@pytest.fixture
def reception(base) -> int:
    with Session(base) as session:
        user = User(email="produits@hotel-panorama.fr", nom="Réception", password_hash="x")
        session.add(user)
        session.commit()
        return user.id


def test_une_base_existante_recoit_un_nom_de_produit_unique(base) -> None:
    Produit.__table__.drop(base)
    create_db_and_tables(base)

    assert "produit" in inspect(base).get_table_names()
    with Session(base) as session:
        session.add(Produit(nom="Café", prix_unitaire_centimes=100))
        session.commit()
        session.add(Produit(nom="Café", prix_unitaire_centimes=200))
        with pytest.raises(IntegrityError):
            session.commit()


def test_creer_et_lister_valide_trie_et_filtre(base) -> None:
    with pytest.raises(ProduitInvalide, match="obligatoire"):
        creer_produit("  ", 100)
    with pytest.raises(ProduitInvalide, match="négatif"):
        creer_produit("Café", -1)
    with pytest.raises(ProduitInvalide, match="entier de centimes"):
        creer_produit("Café", True)  # type: ignore[arg-type]

    the = creer_produit("  Thé  ", 300)
    cafe = creer_produit("Café", 0)
    biscuits = creer_produit("Biscuits", 150)
    assert not definir_produit_actif(biscuits, True)
    assert definir_produit_actif(biscuits, False)

    catalogue = [
        (produit.nom, produit.prix_unitaire_centimes, produit.taux_tva_pour_mille) for produit in lister_produits()
    ]
    assert catalogue == [
        ("Biscuits", 150, 100),
        ("Café", 0, 100),
        ("Thé", 300, 100),
    ]
    assert [produit.id for produit in lister_produits(actifs_seulement=True)] == [cafe, the]
    assert lister_produits()[0].actif is False


def test_le_taux_de_tva_est_enregistre_et_un_taux_inconnu_est_refuse(base) -> None:
    with pytest.raises(ProduitInvalide, match="pas reconnu"):
        creer_produit("Café", 100, taux_tva_pour_mille=12)
    with pytest.raises(ProduitInvalide, match="pas reconnu"):
        creer_produit("Café", 100, taux_tva_pour_mille=True)  # type: ignore[arg-type]

    cafe = creer_produit("Café", 250, taux_tva_pour_mille=55)
    assert lister_produits()[0].taux_tva_pour_mille == 55
    assert not modifier_produit(cafe, "Café", 250, taux_tva_pour_mille=55)
    assert modifier_produit(cafe, "Café", 250, taux_tva_pour_mille=0)
    assert lister_produits()[0].taux_tva_pour_mille == 0
    with pytest.raises(ProduitInvalide, match="pas reconnu"):
        modifier_produit(cafe, "Thé", 400, taux_tva_pour_mille=12)
    reste = [
        (produit.nom, produit.prix_unitaire_centimes, produit.taux_tva_pour_mille) for produit in lister_produits()
    ]
    assert reste == [("Café", 250, 0)]


def test_une_base_existante_recoit_le_taux_de_tva(base) -> None:
    with base.begin() as connexion:
        connexion.exec_driver_sql("DROP TABLE produit")
        connexion.exec_driver_sql(
            "CREATE TABLE produit ("
            "id INTEGER NOT NULL, nom VARCHAR NOT NULL, "
            "prix_unitaire_centimes INTEGER NOT NULL DEFAULT 0, "
            "actif BOOLEAN NOT NULL DEFAULT 1, PRIMARY KEY (id), UNIQUE (nom))"
        )
        connexion.exec_driver_sql(
            "INSERT INTO produit (nom, prix_unitaire_centimes, actif) VALUES ('Café ancien', 250, 1)"
        )
    inspect(base).clear_cache()

    assert "produit.taux_tva_pour_mille" in ajouter_colonnes_manquantes(base)
    assert ajouter_colonnes_manquantes(base) == []
    produit = lister_produits()[0]
    assert (produit.nom, produit.prix_unitaire_centimes, produit.taux_tva_pour_mille, produit.actif) == (
        "Café ancien",
        250,
        100,
        True,
    )


def test_un_doublon_est_refuse_et_le_catalogue_reste_utilisable(base, monkeypatch: pytest.MonkeyPatch) -> None:
    creer_produit("Café", 100)
    with pytest.raises(ProduitInvalide, match="existe déjà"):
        creer_produit("Café", 300)

    monkeypatch.setattr(saisie, "_produit_nom_pris", lambda *_args, **_kwargs: False)
    with pytest.raises(ProduitInvalide, match="existe déjà"):
        creer_produit("Café", 300)
    the = creer_produit("Thé", 200)

    assert [produit.nom for produit in lister_produits()] == ["Café", "Thé"]
    assert the


def test_modifier_protege_l_introuvable_le_doublon_et_l_identique(base, monkeypatch: pytest.MonkeyPatch) -> None:
    cafe = creer_produit("Café", 100)
    the = creer_produit("Thé", 200)

    with pytest.raises(ProduitInvalide, match="introuvable"):
        modifier_produit(999, "Chocolat", 100)
    with pytest.raises(ProduitInvalide, match="existe déjà"):
        modifier_produit(cafe, "Thé", 100)
    assert not modifier_produit(cafe, "Café", 100)

    with monkeypatch.context() as isole:
        isole.setattr(saisie, "_produit_nom_pris", lambda *_args, **_kwargs: False)
        with pytest.raises(ProduitInvalide, match="existe déjà"):
            modifier_produit(cafe, "Thé", 400)
    assert [(produit.id, produit.nom, produit.prix_unitaire_centimes) for produit in lister_produits()] == [
        (cafe, "Café", 100),
        (the, "Thé", 200),
    ]

    assert modifier_produit(cafe, " Chocolat ", 450)
    assert [(produit.nom, produit.prix_unitaire_centimes) for produit in lister_produits()] == [
        ("Chocolat", 450),
        ("Thé", 200),
    ]


def test_vendre_copie_le_prix_accepte_et_garde_les_ventes_passees(reception: int) -> None:
    reservation_id = creer_reservation()
    produit_id = creer_produit("Café", 250)
    ajouter_consommation(reservation_id, "Ancien bar", 1, 300, reception)

    with pytest.raises(ProduitInvalide, match="introuvable"):
        ajouter_consommation_produit(999, produit_id, 1, 250, reception)
    with pytest.raises(ProduitInvalide, match="introuvable"):
        ajouter_consommation_produit(reservation_id, 999, 1, 250, reception)
    with pytest.raises(ProduitInvalide, match="quantité"):
        ajouter_consommation_produit(reservation_id, produit_id, 0, 250, reception)
    with pytest.raises(ProduitInvalide, match="quantité"):
        ajouter_consommation_produit(reservation_id, produit_id, True, 250, reception)  # type: ignore[arg-type]
    with pytest.raises(ProduitInvalide, match="négatif"):
        ajouter_consommation_produit(reservation_id, produit_id, 1, -1, reception)

    vente = ajouter_consommation_produit(reservation_id, produit_id, 2, 200, reception)
    assert modifier_produit(produit_id, "Thé", 900)
    assert definir_produit_actif(produit_id, False)
    with pytest.raises(ProduitInvalide, match="plus en vente"):
        ajouter_consommation_produit(reservation_id, produit_id, 1, 900, reception)
    with pytest.raises(ProduitInvalide, match="introuvable"):
        definir_produit_actif(999, True)

    fiche = fiche_sejour(reservation_id)
    ventes = [
        (ligne["libelle"], ligne["quantite"], ligne["prix_unitaire_centimes"]) for ligne in fiche["consommations"]
    ]
    assert ventes == [("Ancien bar", 1, 300), ("Café", 2, 200)]
    assert fiche["consommations"][1]["id"] == vente
    assert fiche["consommations"][1]["montant"] == 400
    assert fiche["historique"][0]["description"] == f"Consommation ajoutée : 2 × Café ({format_euros(400)})"
    assert [produit.nom for produit in lister_produits(actifs_seulement=True)] == []

    assert definir_produit_actif(produit_id, True)
    ajouter_consommation_produit(reservation_id, produit_id, 1, 900, reception)
    libelles = [ligne["libelle"] for ligne in fiche_sejour(reservation_id)["consommations"]]
    assert libelles == ["Ancien bar", "Café", "Thé"]


def _heure_locale(moment: datetime) -> datetime:
    return (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).astimezone()


def test_modifier_une_consommation_met_a_jour_la_ligne_sans_toucher_au_catalogue(reception: int, base) -> None:
    reservation_id = creer_reservation()
    produit_id = creer_produit("Café", 250)
    vente = ajouter_consommation_produit(reservation_id, produit_id, 2, 200, reception)
    with Session(base) as session:
        ligne = session.get(Consommation, vente)
        ligne.date = datetime(2026, 6, 15, 8, 45, tzinfo=UTC)
        session.add(ligne)
        session.commit()

    avant = _heure_locale(fiche_sejour(reservation_id)["consommations"][0]["date"])
    with pytest.raises(ProduitInvalide, match="introuvable"):
        modifier_consommation(999, 1, 100, avant.date(), reception)
    with pytest.raises(ProduitInvalide, match="quantité"):
        modifier_consommation(vente, 0, 200, avant.date(), reception)
    with pytest.raises(ProduitInvalide, match="quantité"):
        modifier_consommation(vente, True, 200, avant.date(), reception)  # type: ignore[arg-type]
    with pytest.raises(ProduitInvalide, match="négatif"):
        modifier_consommation(vente, 2, -1, avant.date(), reception)
    with pytest.raises(ProduitInvalide, match="pas reconnue"):
        modifier_consommation(vente, 2, 200, datetime(2026, 6, 15, 8, 45), reception)  # type: ignore[arg-type]
    assert not modifier_consommation(vente, 2, 200, avant.date(), reception)
    assert len(fiche_sejour(reservation_id)["historique"]) == 1

    assert modifier_consommation(vente, 3, 150, date(2026, 1, 20), reception)
    fiche = fiche_sejour(reservation_id)
    modifiee = fiche["consommations"][0]
    apres = _heure_locale(modifiee["date"])
    assert (modifiee["libelle"], modifiee["quantite"], modifiee["prix_unitaire_centimes"], modifiee["montant"]) == (
        "Café",
        3,
        150,
        450,
    )
    assert apres.date() == date(2026, 1, 20)
    assert (apres.hour, apres.minute) == (avant.hour, avant.minute)
    assert fiche["totaux"].consommations == 450
    assert fiche["historique"][0]["description"] == (
        f"Consommation modifiée : 3 × Café ({format_euros(450)}) le 20/01/2026"
    )
    assert next(produit.prix_unitaire_centimes for produit in lister_produits() if produit.id == produit_id) == 250
