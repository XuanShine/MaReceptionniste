"""Aperçu, émission, remplacement, PDF et email : ce qu'un séjour laisse après coup."""

import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from uuid import uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import text
from sqlmodel import Session, select

from ma_receptionniste.consultations import fiche_sejour
from ma_receptionniste.db import _preparer_facturation
from ma_receptionniste.facturation import (
    TAUX_TVA_DEFAUT,
    ApercuPerime,
    DestinataireFacture,
    EmissionImpossible,
    EnvoiIndisponible,
    IdentiteFacturation,
    MentionsManquantes,
    PdfIndisponible,
    RemplacementInterdit,
    appliquer_taxe_et_reglements,
    calculer_totaux,
    contenu_apercu,
    contenu_facture,
    destinataire_de_sejour,
    emettre_facture,
    enregistrer_identite,
    ht_depuis_ttc,
    ligne_ttc,
    lire_facture,
    lire_identite,
    lister_factures,
    numero_sans_archive,
    obtenir_facture_courante,
    preparer_apercu,
)
from ma_receptionniste.facturation_email import envoyer_facture
from ma_receptionniste.facturation_odt import (
    AVERTISSEMENT_APERCU,
    chemin_modele,
    contexte_apercu,
    contexte_facture,
    convertir_pdf,
    rendre_odt,
)
from ma_receptionniste.facturation_pdf import dossier_factures, generer_pdf, generer_pdf_apercu
from ma_receptionniste.models import (
    CategorieLigne,
    CompteurFacture,
    FormeJuridique,
    ModeReglement,
    NatureReglement,
    Produit,
    RegimeTVA,
    Reservation,
    TypeDestinataire,
    User,
)
from ma_receptionniste.models import (
    Facture as FactureTable,
)
from ma_receptionniste.saisie import (
    ajouter_reglement,
    ajouter_sejour,
    creer_chambre,
    creer_client,
    creer_produit,
    creer_reservation,
    creer_type_chambre,
    facturer,
)

ARRIVEE = date(2026, 10, 18)
DEPART = date(2026, 10, 20)


@pytest.fixture
def reception(base) -> int:
    with Session(base) as session:
        user = User(email="reception@hotel-panorama.fr", nom="Réception", password_hash="x")
        session.add(user)
        session.commit()
        return user.id


def identite(**ecarts) -> IdentiteFacturation:
    valeurs = dict(
        nom_commercial="Hôtel Panorama",
        denomination="Panorama SAS",
        forme_juridique=FormeJuridique.sas,
        capital_centimes=1_000_000,
        adresse_siege="1 quai du Port\n29200 Brest",
        adresse_facturation=None,
        siren="123456789",
        siret="12345678900012",
        immatriculation="RCS Brest",
        numero_tva="FR12123456789",
        regime_tva=RegimeTVA.assujetti,
        taux_hebergement_pour_mille=100,
        delai_paiement_jours=0,
        conditions_paiement=None,
        escompte=None,
        penalites=None,
    )
    valeurs.update(ecarts)
    return IdentiteFacturation(**valeurs)


def destinataire(**ecarts) -> DestinataireFacture:
    valeurs = dict(
        type=TypeDestinataire.particulier,
        nom="LE CLOEREC",
        adresse="1 rue du Port, 29200 Brest",
        adresse_facturation=None,
        siren=None,
        numero_tva=None,
        reference_commande=None,
    )
    valeurs.update(ecarts)
    return DestinataireFacture(**valeurs)


def sejour_facture(reception: int, *, prix: int = 6882, taux_produit: int = 200) -> int:
    enregistrer_identite(identite())
    reservation_id = creer_reservation(creer_client("LE CLOEREC", adresse="1 rue du Port, 29200 Brest"))
    type_id = creer_type_chambre("Single BB")
    chambre_id = creer_chambre(f"406-{reservation_id}", 1, type_chambre_id=type_id)
    ajouter_sejour(reservation_id, chambre_id, ARRIVEE, DEPART, prix_nuit_centimes=prix, user_id=reception)
    produit_id = creer_produit("Vin", 1200, taux_tva_pour_mille=taux_produit)
    from ma_receptionniste.saisie import ajouter_consommation_produit

    ajouter_consommation_produit(reservation_id, produit_id, 1, 1200, reception)
    return reservation_id


def test_ht_et_ventilation_sur_plusieurs_taux() -> None:
    chambre = ligne_ttc(CategorieLigne.chambre, "Chambre 406", 2, 6882, 100)
    vin = ligne_ttc(CategorieLigne.consommation, "Vin", 1, 1200, 200, remise_centimes=0)
    assert chambre.montant_ttc_centimes == 13764
    assert chambre.montant_ht_centimes == ht_depuis_ttc(13764, 100)
    assert chambre.montant_tva_centimes == 13764 - chambre.montant_ht_centimes
    assert vin.montant_ht_centimes == 1000
    assert vin.montant_tva_centimes == 200
    totaux = appliquer_taxe_et_reglements(
        calculer_totaux([chambre, vin]),
        400,
        [],
    )
    assert totaux.total_prestations_ttc_centimes == 13764 + 1200
    assert totaux.taxe_sejour_centimes == 400
    assert totaux.total_a_payer_centimes == 13764 + 1200 + 400
    assert {ventilation.taux_tva_pour_mille for ventilation in totaux.ventilations} == {100, 200}
    assert totaux.total_ht_centimes + totaux.total_tva_centimes == totaux.total_prestations_ttc_centimes


def test_une_remise_reduit_le_ttc_avant_la_tva() -> None:
    ligne = ligne_ttc(CategorieLigne.consommation, "Café", 2, 500, 100, remise_centimes=100)
    assert ligne.montant_ttc_centimes == 900
    assert ligne.montant_ht_centimes + ligne.montant_tva_centimes == 900


def test_enregistrer_l_identite_autorise_une_fiche_incomplete(base) -> None:
    enregistrer_identite(identite(denomination=None, siren=None, siret=None))
    assert lire_identite().nom_commercial == "Hôtel Panorama"
    with pytest.raises(MentionsManquantes) as erreur:
        preparer_apercu(creer_reservation(creer_client("LE CLOEREC", adresse="1 rue")), destinataire())
    assert "dénomination sociale" in erreur.value.mentions


def test_l_apercu_n_ecrit_rien(reception: int) -> None:
    reservation_id = sejour_facture(reception)
    apercu = preparer_apercu(reservation_id, destinataire())
    fiche = fiche_sejour(reservation_id)
    assert fiche["reservation"]["numero_facture"] is None
    assert fiche["reservation"]["facturation"] is None
    assert obtenir_facture_courante(reservation_id) is None
    assert apercu.empreinte
    assert "Aperçu — facture non émise" in contenu_apercu(apercu)
    assert "adulte" not in " ".join(contenu_apercu(apercu)).lower()
    assert "1. Chambres" in contenu_apercu(apercu)
    assert any(ligne.startswith("Chambre 406-") and "Single BB" in ligne for ligne in contenu_apercu(apercu))
    assert "Taxe de séjour (hors base TVA)" in "\n".join(contenu_apercu(apercu))
    assert "Acomptes déjà facturés : aucun." in contenu_apercu(apercu)


def test_emission_fige_les_montants_et_le_nom(reception: int) -> None:
    reservation_id = sejour_facture(reception)
    apercu = preparer_apercu(reservation_id, destinataire(nom="Facturation Client"))
    facture = emettre_facture(apercu, uuid4(), user_id=reception)
    ht_chambre = next(
        ligne.montant_ht_centimes for ligne in facture.lignes if ligne.categorie is CategorieLigne.chambre
    )
    from ma_receptionniste.saisie import modifier_sejour

    ligne = fiche_sejour(reservation_id)["lignes"][0]
    modifier_sejour(
        ligne["id"],
        ligne["chambre_id"],
        ARRIVEE,
        DEPART,
        2,
        0,
        1000,
        None,
        user_id=reception,
    )
    enregistrer_identite(identite(denomination="Autre SAS"))
    relue = lire_facture(facture.id)
    assert relue.numero == 1
    assert relue.destinataire.nom == "Facturation Client"
    assert relue.identite.denomination == "Panorama SAS"
    chambre = next(ligne for ligne in relue.lignes if ligne.categorie is CategorieLigne.chambre)
    assert chambre.montant_ht_centimes == ht_chambre
    assert fiche_sejour(reservation_id)["reservation"]["facturation"] == "Facturation Client"
    assert fiche_sejour(reservation_id)["reservation"]["numero_facture"] == 1
    assert "Facture n° 1 émise" in [note["description"] for note in fiche_sejour(reservation_id)["historique"]]
    with pytest.raises(EmissionImpossible, match="déjà émise"):
        emettre_facture(apercu, uuid4())


def test_un_changement_depuis_l_apercu_n_emet_rien(reception: int) -> None:
    reservation_id = sejour_facture(reception)
    apercu = preparer_apercu(reservation_id, destinataire())
    from ma_receptionniste.saisie import modifier_sejour

    ligne = fiche_sejour(reservation_id)["lignes"][0]
    modifier_sejour(ligne["id"], ligne["chambre_id"], ARRIVEE, DEPART, 1, 0, 1000, None, user_id=reception)
    with pytest.raises(ApercuPerime):
        emettre_facture(apercu, uuid4())
    assert obtenir_facture_courante(reservation_id) is None
    assert fiche_sejour(reservation_id)["reservation"]["numero_facture"] is None
    assert fiche_sejour(reservation_id)["reservation"]["facturation"] is None


def test_la_meme_cle_ne_cree_pas_une_seconde_facture(reception: int) -> None:
    reservation_id = sejour_facture(reception)
    apercu = preparer_apercu(reservation_id, destinataire())
    cle = uuid4()
    premiere = emettre_facture(apercu, cle)
    seconde = emettre_facture(apercu, cle)
    assert premiere.id == seconde.id
    assert len(lister_factures(reservation_id)) == 1


def test_deux_sejours_prennent_deux_numeros_sans_trou(reception: int, base) -> None:
    premiere = sejour_facture(reception)
    seconde = creer_reservation(creer_client("MARTIN", adresse="2 rue du Port"))
    emettre_facture(preparer_apercu(premiere, destinataire()), uuid4())
    emettre_facture(preparer_apercu(seconde, destinataire(nom="MARTIN")), uuid4())
    with Session(base) as session:
        numeros = set(session.exec(select(FactureTable.numero)).all())
    assert numeros == {1, 2}


def test_un_numero_deja_pose_n_est_pas_reutilise(reception: int, base) -> None:
    reservation_id = creer_reservation(creer_client("ANCIEN", adresse="3 rue du Port"))
    with Session(base) as session:
        reservation = session.get(Reservation, reservation_id)
        reservation.numero_facture = 7
        reservation.date_facture = date.today()
        session.add(reservation)
        session.commit()
    assert facturer(reservation_id, reception) == 7
    assert numero_sans_archive(reservation_id).numero == 7
    autre = creer_reservation(creer_client("SUIVANT", adresse="4 rue du Port"))
    enregistrer_identite(identite())
    suivante = emettre_facture(preparer_apercu(autre, destinataire(nom="SUIVANT")), uuid4())
    assert suivante.numero == 8
    assert fiche_sejour(reservation_id)["reservation"]["numero_facture"] == 7


def test_le_compteur_reprend_le_maximum_apres_suppression_de_la_ligne(base) -> None:
    reservation_id = creer_reservation(creer_client("ANCIEN"))
    with Session(base) as session:
        reservation = session.get(Reservation, reservation_id)
        reservation.numero_facture = 4
        session.add(reservation)
        session.commit()
        session.execute(text("DELETE FROM compteur_facture"))
        session.commit()
    _preparer_facturation(base)
    with Session(base) as session:
        assert session.get(CompteurFacture, 1).dernier_numero == 4


def test_remplacement_d_une_facture_impayee(reception: int) -> None:
    reservation_id = sejour_facture(reception)
    premiere = emettre_facture(preparer_apercu(reservation_id, destinataire()), uuid4())
    apercu = preparer_apercu(reservation_id, destinataire(nom="LE CLOEREC"), remplace_id=premiere.id)
    assert f"Annule et remplace la facture n° 1 du {date.today():%d/%m/%Y}" in contenu_apercu(apercu)
    seconde = emettre_facture(apercu, uuid4())
    assert seconde.numero == 2
    assert seconde.courante is True
    assert lire_facture(premiere.id).courante is False
    assert fiche_sejour(reservation_id)["reservation"]["numero_facture"] == 2
    assert [facture.numero for facture in lister_factures(reservation_id)] == [1, 2]
    with pytest.raises(RemplacementInterdit):
        preparer_apercu(reservation_id, destinataire(), remplace_id=premiere.id)


def test_une_facture_reglee_ou_partielle_ne_se_remplace_pas(reception: int) -> None:
    reservation_id = sejour_facture(reception)
    ajouter_reglement(reservation_id, ModeReglement.carte, 100, reception)
    facture = emettre_facture(preparer_apercu(reservation_id, destinataire()), uuid4())
    with pytest.raises(RemplacementInterdit, match="partiellement"):
        preparer_apercu(reservation_id, destinataire(), remplace_id=facture.id)
    assert len(lister_factures(reservation_id)) == 1


def test_une_facture_soldee_cite_l_avoir(reception: int) -> None:
    reservation_id = sejour_facture(reception)
    apercu = preparer_apercu(reservation_id, destinataire())
    ajouter_reglement(reservation_id, ModeReglement.carte, apercu.totaux.total_a_payer_centimes, reception)
    facture = emettre_facture(preparer_apercu(reservation_id, destinataire()), uuid4())
    with pytest.raises(RemplacementInterdit, match="déjà réglée"):
        preparer_apercu(reservation_id, destinataire(), remplace_id=facture.id)


def test_un_reglement_apres_emission_bloque_le_remplacement(reception: int) -> None:
    reservation_id = sejour_facture(reception)
    facture = emettre_facture(preparer_apercu(reservation_id, destinataire()), uuid4())
    ajouter_reglement(reservation_id, ModeReglement.especes, 500, reception)
    with pytest.raises(RemplacementInterdit):
        preparer_apercu(reservation_id, destinataire(), remplace_id=facture.id)


def test_la_date_ne_peut_pas_reculer(reception: int, base) -> None:
    reservation_id = sejour_facture(reception)
    emettre_facture(preparer_apercu(reservation_id, destinataire()), uuid4())
    with Session(base) as session:
        facture = session.exec(select(FactureTable)).one()
        facture.date_emission = date.today() + timedelta(days=1)
        session.add(facture)
        session.commit()
    autre = creer_reservation(creer_client("AUTRE", adresse="5 rue du Port"))
    with pytest.raises(EmissionImpossible, match="antérieure"):
        emettre_facture(preparer_apercu(autre, destinataire(nom="AUTRE")), uuid4())
    with Session(base) as session:
        assert session.get(CompteurFacture, 1).dernier_numero == 1


def test_deux_emissions_concurrentes_n_attribuent_qu_un_numero(tmp_path, monkeypatch) -> None:
    from sqlalchemy import event
    from sqlmodel import create_engine

    from ma_receptionniste import db
    from ma_receptionniste.db import create_db_and_tables

    moteur = create_engine(
        f"sqlite:///{tmp_path}/concurrent.db",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(moteur, "connect")
    def _cles(connexion, _) -> None:
        connexion.execute("PRAGMA foreign_keys=ON")

    create_db_and_tables(moteur)
    monkeypatch.setattr(db, "engine", moteur)
    with Session(moteur) as session:
        utilisateur = User(email="concurrent@hotel.fr", nom="Réception", password_hash="x")
        session.add(utilisateur)
        session.commit()
        user_id = utilisateur.id
    reservation_id = sejour_facture(user_id)
    apercu = preparer_apercu(reservation_id, destinataire())

    def emettre():
        try:
            return emettre_facture(apercu, uuid4()).numero
        except EmissionImpossible:
            courante = obtenir_facture_courante(reservation_id)
            return None if courante is None else courante.numero

    with ThreadPoolExecutor(max_workers=2) as pool:
        numeros = list(pool.map(lambda _: emettre(), range(2)))
    assert sorted(numeros) == [1, 1]
    assert len(lister_factures(reservation_id)) == 1


def test_pdf_apercu_et_archive_stable(reception: int) -> None:
    reservation_id = sejour_facture(reception)
    apercu = preparer_apercu(reservation_id, destinataire())
    premier = generer_pdf_apercu(apercu)
    assert premier.startswith(b"%PDF")
    assert generer_pdf_apercu(apercu).startswith(b"%PDF")
    facture = emettre_facture(apercu, uuid4())
    chemin = generer_pdf(facture.id)
    empreinte = hashlib.sha256(chemin.read_bytes()).hexdigest()
    assert lire_facture(facture.id).pdf_empreinte == empreinte
    chemin.unlink()
    with pytest.raises(PdfIndisponible, match="Restaurez"):
        generer_pdf(facture.id)
    assert lire_facture(facture.id).pdf_empreinte == empreinte
    chemin.write_bytes(premier)
    chemin.write_bytes(b"modifie")
    with pytest.raises(PdfIndisponible, match="modifié"):
        generer_pdf(facture.id)
    assert "Aperçu — facture non émise" not in contenu_facture(lire_facture(facture.id))


def test_echec_pdf_puis_meme_cle(reception: int, monkeypatch) -> None:
    reservation_id = sejour_facture(reception)
    apercu = preparer_apercu(reservation_id, destinataire())
    cle = uuid4()
    appels = {"n": 0}
    import ma_receptionniste.facturation_pdf as pdf

    original = pdf.generer_pdf

    def fragile(facture_id: int):
        appels["n"] += 1
        if appels["n"] == 1:
            raise PdfIndisponible("disque plein")
        return original(facture_id)

    monkeypatch.setattr(pdf, "generer_pdf", fragile)
    with pytest.raises(PdfIndisponible):
        emettre_facture(apercu, cle)
    assert obtenir_facture_courante(reservation_id).numero == 1
    reprise = emettre_facture(apercu, cle)
    assert reprise.numero == 1
    assert reprise.pdf_empreinte
    assert len(lister_factures(reservation_id)) == 1


def test_email_sans_serveur_adresse_invalide_et_echec(reception: int, monkeypatch) -> None:
    monkeypatch.delenv("SMTP_HOST", raising=False)
    reservation_id = sejour_facture(reception)
    facture = emettre_facture(preparer_apercu(reservation_id, destinataire()), uuid4())
    with pytest.raises(EnvoiIndisponible, match="pas configuré"):
        import asyncio

        asyncio.run(envoyer_facture(facture.id, "client@hotel.fr"))
    monkeypatch.setenv("SMTP_HOST", "smtp.exemple.fr")
    with pytest.raises(EnvoiIndisponible, match="pas valide"):
        asyncio.run(envoyer_facture(facture.id, "pas-un-email"))

    class FauxSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            pass

        def send_message(self, message):
            raise TimeoutError("réseau")

    import ma_receptionniste.facturation_email as courrier

    monkeypatch.setattr(courrier.smtplib, "SMTP", FauxSMTP)
    with pytest.raises(EnvoiIndisponible, match="pas été confirmé"):
        asyncio.run(envoyer_facture(facture.id, "client@hotel.fr"))
    assert len(lister_factures(reservation_id)) == 1
    descriptions = [note["description"] for note in fiche_sejour(reservation_id)["historique"]]
    assert any("non confirmé" in description for description in descriptions)

    envoyes = []

    class SMTPOk(FauxSMTP):
        def send_message(self, message):
            envoyes.append(message)

    monkeypatch.setattr(courrier.smtplib, "SMTP", SMTPOk)
    asyncio.run(envoyer_facture(facture.id, "client@hotel.fr"))
    assert envoyes[0]["To"] == "client@hotel.fr"
    assert len(lister_factures(reservation_id)) == 1


def test_professionnel_et_franchise(reception: int) -> None:
    enregistrer_identite(
        identite(
            regime_tva=RegimeTVA.franchise,
            numero_tva=None,
            forme_juridique=FormeJuridique.ei,
            capital_centimes=None,
        )
    )
    reservation_id = creer_reservation(creer_client("SOCIETE", adresse="10 rue Nationale, 75001 Paris"))
    pro = destinataire(
        type=TypeDestinataire.professionnel,
        nom="SOCIETE",
        adresse="10 rue Nationale, 75001 Paris",
        siren="987654321",
        reference_commande="BC-1",
    )
    apercu = preparer_apercu(reservation_id, pro)
    texte = "\n".join(contenu_apercu(apercu))
    assert "TVA non applicable, article 293 B du CGI" in texte
    assert "indemnité forfaitaire de recouvrement de 40 €" in texte
    assert "Bon de commande BC-1" in texte
    assert "SIREN client 987654321" in texte


def test_le_taux_de_la_consommation_reste_celui_de_la_vente(reception: int, base) -> None:
    reservation_id = sejour_facture(reception, taux_produit=200)
    from ma_receptionniste.saisie import modifier_produit

    apercu = preparer_apercu(reservation_id, destinataire())
    vin = next(ligne for ligne in apercu.lignes if ligne.libelle == "Vin")
    assert vin.taux_tva_pour_mille == 200
    assert TAUX_TVA_DEFAUT == 100
    with Session(base) as session:
        produit_id = session.exec(select(Produit).where(Produit.nom == "Vin")).one().id
    modifier_produit(produit_id, "Vin", 1200, taux_tva_pour_mille=100)
    assert preparer_apercu(reservation_id, destinataire()).lignes[-1].taux_tva_pour_mille == 200


def test_remboursement_negatif(reception: int) -> None:
    reservation_id = sejour_facture(reception)
    ajouter_reglement(reservation_id, ModeReglement.carte, -300, reception)
    apercu = preparer_apercu(reservation_id, destinataire())
    assert apercu.reglements[0].nature is NatureReglement.remboursement
    assert "Remboursement" in "\n".join(contenu_apercu(apercu))


def test_facturation_client_accepte_nimporte_quel_texte(reception: int) -> None:
    reservation_id = sejour_facture(reception)
    for nom in ("", "n'importe quoi", "Dupond & Fils <hôtel>"):
        apercu = preparer_apercu(reservation_id, destinataire(nom=nom, adresse="", siren="abc", numero_tva="???"))
        assert apercu.destinataire.nom == nom
        assert apercu.destinataire.adresse == ""
    facture = emettre_facture(
        preparer_apercu(reservation_id, destinataire(nom="texte libre", adresse="")),
        uuid4(),
    )
    assert lire_facture(facture.id).destinataire.nom == "texte libre"


def test_prefill_nom(reception: int) -> None:
    reservation_id = creer_reservation(creer_client("LE CLOEREC", adresse="1 rue"))
    from ma_receptionniste.saisie import enregistrer_fiche

    assert destinataire_de_sejour(reservation_id).nom == ""
    enregistrer_fiche(reservation_id, reception, {"nom_occupant": "Occupant Seul"})
    assert destinataire_de_sejour(reservation_id).nom == "Occupant Seul"
    enregistrer_fiche(reservation_id, reception, {"facturation": "Facturation Client"})
    assert destinataire_de_sejour(reservation_id).nom == "Facturation Client"


def test_contexte_apercu_sans_numero_et_facture_figee(reception: int) -> None:
    reservation_id = sejour_facture(reception)
    apercu = preparer_apercu(
        reservation_id,
        destinataire(nom="Dupond & Fils <hôtel>", type=TypeDestinataire.professionnel, siren="123456789"),
    )
    contexte = contexte_apercu(apercu)
    assert contexte["facture"]["numero"] == ""
    assert contexte["facture"]["date_emission"] == ""
    assert contexte["facture"]["avertissement"] == AVERTISSEMENT_APERCU
    assert contexte["client"]["nom"] == "Dupond & Fils <hôtel>"
    assert {ligne["taux"] for ligne in contexte["ventilations"]} >= {"10\u202f%", "20\u202f%"}
    assert contexte["totaux"]["taxe_sejour"]
    assert contexte["acomptes"] == "Acomptes déjà facturés : aucun."
    assert contexte["mentions"]
    assert lister_factures(reservation_id) == []
    facture = emettre_facture(apercu, uuid4())
    figee = contexte_facture(lire_facture(facture.id))
    assert figee["facture"]["numero"] == "1"
    assert figee["facture"]["avertissement"] == ""
    assert figee["client"]["nom"] == "Dupond & Fils <hôtel>"
    assert "Annule et remplace" not in figee["facture"]["remplacement"]


def test_remplacement_dans_le_contexte(reception: int) -> None:
    reservation_id = sejour_facture(reception)
    ancienne = emettre_facture(preparer_apercu(reservation_id, destinataire()), uuid4())
    suite = preparer_apercu(reservation_id, destinataire(), remplace_id=ancienne.id)
    contexte = contexte_apercu(suite)
    assert f"Annule et remplace la facture n° {ancienne.numero} du" in contexte["facture"]["remplacement"]


def test_rendu_echappe_les_caracteres(reception: int, tmp_path) -> None:
    reservation_id = sejour_facture(reception)
    apercu = preparer_apercu(reservation_id, destinataire(nom="Dupond & Fils <hôtel>"))
    odt = rendre_odt(contexte_apercu(apercu), tmp_path / "apercu.odt")
    with ZipFile(odt) as archive:
        xml = archive.read("content.xml").decode()
    assert "Dupond &amp; Fils" in xml
    assert "<hôtel>" not in xml
    assert "{{" not in xml


def test_modele_independant_du_repertoire(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert chemin_modele().is_file()
    assert chemin_modele().name == "facture_hotel.odt"


def test_apercu_necrit_pas_d_archive(reception: int) -> None:
    reservation_id = sejour_facture(reception)
    generer_pdf_apercu(preparer_apercu(reservation_id, destinataire()))
    assert list(dossier_factures().glob("*.pdf")) == []
    assert lister_factures(reservation_id) == []


def test_generation_simultanee_une_archive(reception: int) -> None:
    from ma_receptionniste.db import get_session

    reservation_id = sejour_facture(reception)
    facture = emettre_facture(preparer_apercu(reservation_id, destinataire()), uuid4())
    (dossier_factures() / "facture-1.pdf").unlink()
    with get_session() as session:
        ligne = session.get(FactureTable, facture.id)
        ligne.pdf_empreinte = None
        ligne.pdf_chemin = None
        session.add(ligne)
        session.commit()

    def produire(_):
        return generer_pdf(facture.id).read_bytes()

    with ThreadPoolExecutor(max_workers=2) as pool:
        rendus = list(pool.map(produire, range(2)))
    archive = dossier_factures() / "facture-1.pdf"
    assert rendus[0] == rendus[1] == archive.read_bytes()
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == lire_facture(facture.id).pdf_empreinte


def test_conversion_timeout_et_binaire_absent(monkeypatch, tmp_path) -> None:
    import shutil

    odt = tmp_path / "facture.odt"
    odt.write_bytes(b"odt")
    monkeypatch.setattr(shutil, "which", lambda nom: "/usr/bin/libreoffice")

    def trop_long(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="libreoffice", timeout=45)

    monkeypatch.setattr(subprocess, "run", trop_long)
    with pytest.raises(PdfIndisponible, match="délai"):
        convertir_pdf(odt, tmp_path)
    monkeypatch.setattr(shutil, "which", lambda nom: None)
    with pytest.raises(PdfIndisponible, match="introuvable"):
        convertir_pdf(odt, tmp_path)
