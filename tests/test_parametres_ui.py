import asyncio
from datetime import date, timedelta

import pytest
from nicegui import ui
from nicegui.testing import User
from sqlmodel import Session

from ma_receptionniste.auth import register_user
from ma_receptionniste.consultations import ecran_parametres
from ma_receptionniste.models import Chambre, ChambreVirtuelle, Client, Reservation, Sejour, TypeChambre
from ma_receptionniste.wubook import ImportWubookImpossible


async def test_les_parametres_affichent_le_wubook_id(user: User, base) -> None:
    with Session(base) as session:
        register_user(session, "parametres@hotel-panorama.fr", "Réception", "panorama-parametres")
        double = TypeChambre(libelle="Double", wubook_id=12345)
        session.add(double)
        session.add(TypeChambre(libelle="Suite"))
        session.commit()
        session.refresh(double)
        type_id = double.id
        session.add(
            ChambreVirtuelle(type_chambre_id=type_id, nom_raccourci="V1", prix_defaut=80, prix_mini=50, wubook_id=67890)
        )
        session.add(ChambreVirtuelle(type_chambre_id=type_id, nom_raccourci="V2", prix_defaut=90, prix_mini=60))
        session.commit()

    types = {ligne["libelle"]: ligne for ligne in ecran_parametres()["types"]}
    assert types["Double"]["wubook_id"] == 12345
    assert types["Suite"]["wubook_id"] is None
    assert [virtuelle["wubook_id"] for virtuelle in types["Double"]["virtuelles"]] == [67890, None]

    await user.open("/login")
    user.find("Email").type("parametres@hotel-panorama.fr")
    user.find("Mot de passe").type("panorama-parametres")
    user.find("Se connecter").click()
    await user.should_see("Aujourd'hui", retries=30)

    await user.open("/parametres")
    await user.should_see("wubook_id")
    await user.should_see("12345")
    await user.should_see("—")
    with user.scope(marker=f"virtuelles-{type_id}"):
        await user.should_see("wubook_id")
        await user.should_see("67890")
        await user.should_see("—")


async def _ouvrir_parametres(user: User, base) -> None:
    with Session(base) as session:
        register_user(session, "import@hotel-panorama.fr", "Réception", "panorama-import")
    await user.open("/login")
    user.find("Email").type("import@hotel-panorama.fr")
    user.find("Mot de passe").type("panorama-import")
    user.find("Se connecter").click()
    await user.should_see("Aujourd'hui", retries=30)
    await user.open("/parametres")


async def test_import_demande_confirmation_et_rafraichit_la_page(user: User, base, monkeypatch) -> None:
    appels = []

    def importer():
        appels.append(True)
        with Session(base) as session:
            session.add(TypeChambre(libelle="Type importé", wubook_id=54321))
            session.commit()
        return 1, 0

    monkeypatch.setattr("ma_receptionniste.pages.parametres.mettre_a_jour_types_wubook", importer)
    await _ouvrir_parametres(user, base)
    await user.should_not_see("Nom raccourci")
    await user.should_not_see("Prix par défaut")
    await user.should_see("Aucun type. Importez")
    user.find("Mettre à jour les types de chambres de Wubook").click()
    await user.should_see("Remplacer le catalogue local ?")
    assert appels == []
    user.find("Annuler").click()
    assert appels == []
    user.find("Mettre à jour les types de chambres de Wubook").click()
    user.find("Remplacer et importer").click()
    await user.should_see("1 types de chambres et 0 chambres virtuelles importés")
    await user.should_see("Type importé")
    await user.should_see("54321")
    assert appels == [True]


async def test_echec_import_affiche_une_erreur_et_permet_de_reessayer(user: User, base, monkeypatch) -> None:
    appels = []

    def echouer():
        appels.append(True)
        raise ImportWubookImpossible(f"Wubook indisponible (essai {len(appels)}), catalogue conservé")

    monkeypatch.setattr("ma_receptionniste.pages.parametres.mettre_a_jour_types_wubook", echouer)
    await _ouvrir_parametres(user, base)
    user.find("Mettre à jour les types de chambres de Wubook").click()
    user.find("Remplacer et importer").click()
    await user.should_see("Wubook indisponible (essai 1), catalogue conservé")
    user.find("Remplacer et importer").click()
    await user.should_see("Wubook indisponible (essai 2), catalogue conservé")
    await user.should_see("Remplacer le catalogue local ?")
    assert len(appels) == 2


@pytest.fixture
def catalogue_parametres(base) -> tuple[int, int, int]:
    with Session(base) as session:
        type_chambre = TypeChambre(libelle="Double", description="Vue jardin")
        session.add(type_chambre)
        session.flush()
        virtuelle = ChambreVirtuelle(
            type_chambre_id=type_chambre.id,
            nom_raccourci="V1",
            description="Avec déjeuner",
            prix_defaut=80,
            prix_mini=50,
        )
        chambre = Chambre(nom="101", position=1, etage=1, type_chambre_id=type_chambre.id)
        session.add_all([virtuelle, chambre])
        session.commit()
        return type_chambre.id, virtuelle.id, chambre.id


@pytest.mark.parametrize("texte,evenement", [("Vue mer", "blur"), ("", "keydown.enter")])
async def test_description_type_modifiable(user: User, base, catalogue_parametres, texte, evenement) -> None:
    type_id, _, _ = catalogue_parametres
    await _ouvrir_parametres(user, base)
    await user.should_see("Vue jardin")
    user.find(marker=f"description-type-{type_id}").clear().type(texte).trigger(evenement)
    await user.should_see("Type enregistré")
    assert ecran_parametres()["types"][0]["description"] == texte
    await user.open("/parametres")
    champ = user.find(marker=f"description-type-{type_id}")
    assert next(iter(champ.elements)).value == texte


@pytest.mark.parametrize("texte,evenement", [("Sans déjeuner", "keydown.enter"), ("", "blur")])
async def test_description_virtuelle_modifiable(user: User, base, catalogue_parametres, texte, evenement) -> None:
    type_id, virtuelle_id, _ = catalogue_parametres
    await _ouvrir_parametres(user, base)
    with user.scope(marker=f"virtuelles-{type_id}"):
        await user.should_see("Avec déjeuner")
        user.find(marker=f"description-virtuelle-{virtuelle_id}").clear().type(texte).trigger(evenement)
    await user.should_see("Chambre virtuelle enregistrée")
    assert ecran_parametres()["types"][0]["virtuelles"][0]["description"] == texte
    await user.open("/parametres")
    champ = user.find(marker=f"description-virtuelle-{virtuelle_id}")
    assert next(iter(champ.elements)).value == texte


@pytest.mark.parametrize("etage,evenement", [(-1, "blur"), (0, "keydown.enter")])
async def test_etage_chambre_modifiable(user: User, base, catalogue_parametres, etage, evenement) -> None:
    _, _, chambre_id = catalogue_parametres
    await _ouvrir_parametres(user, base)
    user.find(marker=f"etage-chambre-{chambre_id}").clear().type(str(etage)).trigger(evenement)
    await user.should_see("Étage enregistré")
    assert ecran_parametres()["chambres"][0]["etage"] == etage
    await user.open("/parametres")
    champ = user.find(marker=f"etage-chambre-{chambre_id}")
    assert next(iter(champ.elements)).value == etage


async def test_creation_chambre_avec_etage(user: User, base) -> None:
    await _ouvrir_parametres(user, base)
    with user.scope(marker="ajout-chambre"):
        user.find("Nom ou numéro *").type("202")
        user.find(marker="etage-nouvelle-chambre").clear().type("2")
        user.find("Ajouter").click()
    await user.should_see("Chambre ajoutée")
    assert ecran_parametres()["chambres"][0]["etage"] == 2


async def test_creation_virtuelle_avec_description(user: User, base, catalogue_parametres) -> None:
    type_id, _, _ = catalogue_parametres
    await _ouvrir_parametres(user, base)
    with user.scope(marker=f"ajout-virtuelle-{type_id}"):
        user.find(marker="raccourci").type("V2")
        user.find(marker="prix").type("80")
        user.find(marker="prix-mini").type("50")
        user.find(marker=f"description-nouvelle-virtuelle-{type_id}").type("Avec dîner")
        user.find("Ajouter une chambre virtuelle").click()
    await user.should_see("Chambre virtuelle ajoutée")
    virtuelles = ecran_parametres()["types"][0]["virtuelles"]
    assert next(ligne for ligne in virtuelles if ligne["nom_raccourci"] == "V2")["description"] == "Avec dîner"


async def test_creation_chambre_avec_plusieurs_virtuelles(user: User, base, catalogue_parametres) -> None:
    _, virtuelle_id, _ = catalogue_parametres
    with Session(base) as session:
        autre_type = TypeChambre(libelle="Suite")
        session.add(autre_type)
        session.flush()
        virtuelle = ChambreVirtuelle(type_chambre_id=autre_type.id, nom_raccourci="V2", prix_defaut=90, prix_mini=60)
        session.add(virtuelle)
        session.commit()
        autre_id = virtuelle.id

    await _ouvrir_parametres(user, base)
    with user.scope(marker="ajout-chambre"):
        user.find("Nom ou numéro *").type("202")
        select = next(iter(user.find(marker="virtuelles-nouvelle-chambre").elements))
        assert set(select.options) == {virtuelle_id, autre_id}
        select.set_value([virtuelle_id, autre_id])
        user.find("Ajouter").click()
    await user.should_see("Chambre ajoutée")
    chambre = next(ligne for ligne in ecran_parametres()["chambres"] if ligne["nom"] == "202")
    assert set(chambre["chambres_virtuelles_ids"]) == {virtuelle_id, autre_id}
    await user.open("/parametres")
    select = next(iter(user.find(marker=f"virtuelles-chambre-{chambre['id']}").elements))
    assert set(select.value) == {virtuelle_id, autre_id}


async def test_modifier_et_vider_les_virtuelles_d_une_chambre(user: User, base, catalogue_parametres) -> None:
    _, virtuelle_id, chambre_id = catalogue_parametres
    await _ouvrir_parametres(user, base)
    select = next(iter(user.find(marker=f"virtuelles-chambre-{chambre_id}").elements))
    assert select.value == []
    select.set_value([virtuelle_id])
    await user.should_see("Chambres virtuelles enregistrées")
    assert ecran_parametres()["chambres"][0]["chambres_virtuelles_ids"] == [virtuelle_id]

    await user.open("/parametres")
    select = next(iter(user.find(marker=f"virtuelles-chambre-{chambre_id}").elements))
    assert select.value == [virtuelle_id]
    select.set_value([])
    async with asyncio.timeout(2):
        while ecran_parametres()["chambres"][0]["chambres_virtuelles_ids"]:
            await asyncio.sleep(0.02)
    assert ecran_parametres()["chambres"][0]["chambres_virtuelles_ids"] == []


async def test_disponibilite_du_jour_calculee_et_non_modifiable(user: User, base, catalogue_parametres) -> None:
    type_id, _, chambre_id = catalogue_parametres
    with Session(base) as session:
        type_ = session.get(TypeChambre, type_id)
        type_.disponibilite = 99
        session.add(type_)
        client = Client(nom="Occupant")
        session.add(client)
        session.flush()
        reservation = Reservation(client_id=client.id)
        session.add(reservation)
        session.flush()
        session.add(
            Sejour(
                reservation_id=reservation.id,
                chambre_id=chambre_id,
                date_debut=date.today(),
                date_fin=date.today() + timedelta(days=1),
            )
        )
        session.commit()

    await _ouvrir_parametres(user, base)

    await user.should_see("Disponibles aujourd’hui")
    label = next(iter(user.find(marker=f"disponibilite-type-{type_id}").elements))
    assert isinstance(label, ui.label)
    assert label.text == "0"
    with Session(base) as session:
        assert session.get(TypeChambre, type_id).disponibilite == 99


async def test_disponibilites_actualisees_apres_creation_et_reaffectation(
    user: User, base, catalogue_parametres
) -> None:
    type_id, _, _ = catalogue_parametres
    with Session(base) as session:
        suite = TypeChambre(libelle="Suite")
        session.add(suite)
        session.commit()
        suite_id = suite.id
    await _ouvrir_parametres(user, base)
    assert next(iter(user.find(marker=f"disponibilite-type-{type_id}").elements)).text == "1"
    assert next(iter(user.find(marker=f"disponibilite-type-{suite_id}").elements)).text == "0"

    with user.scope(marker="ajout-chambre"):
        user.find("Nom ou numéro *").type("202")
        select = next(element for element in user.find(ui.select).elements if element.label == "Type")
        select.set_value(type_id)
        user.find("Ajouter").click()
    await user.should_see("Chambre ajoutée")
    assert next(iter(user.find(marker=f"disponibilite-type-{type_id}").elements)).text == "2"

    chambre_id = next(ligne["id"] for ligne in ecran_parametres()["chambres"] if ligne["nom"] == "202")
    next(iter(user.find(marker=f"type-chambre-{chambre_id}").elements)).set_value(suite_id)
    await user.should_see("Type enregistré")
    assert next(iter(user.find(marker=f"disponibilite-type-{type_id}").elements)).text == "1"
    assert next(iter(user.find(marker=f"disponibilite-type-{suite_id}").elements)).text == "1"


async def test_timer_actualise_les_labels_sans_effacer_la_saisie(
    user: User, base, catalogue_parametres, monkeypatch
) -> None:
    type_id, _, chambre_id = catalogue_parametres
    await _ouvrir_parametres(user, base)
    label = next(iter(user.find(marker=f"disponibilite-type-{type_id}").elements))
    champ = next(iter(user.find(marker=f"description-type-{type_id}").elements))
    champ.set_value("Saisie en cours")
    timer = next(iter(user.find(marker="actualisation-disponibilites").elements))
    assert timer.interval == 30

    aujourd_hui = date.today()
    with Session(base) as session:
        client = Client(nom="Réservation externe")
        session.add(client)
        session.flush()
        reservation = Reservation(client_id=client.id)
        session.add(reservation)
        session.flush()
        session.add(
            Sejour(
                reservation_id=reservation.id,
                chambre_id=chambre_id,
                date_debut=aujourd_hui,
                date_fin=aujourd_hui + timedelta(days=1),
            )
        )
        session.commit()

    await timer.callback()
    assert label.text == "0"
    assert next(iter(user.find(marker=f"description-type-{type_id}").elements)) is champ
    assert champ.value == "Saisie en cours"

    class Demain(date):
        @classmethod
        def today(cls):
            return aujourd_hui + timedelta(days=1)

    monkeypatch.setattr("ma_receptionniste.pages.parametres.date", Demain)
    await timer.callback()
    assert label.text == "1"
    assert champ.value == "Saisie en cours"
