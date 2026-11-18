from decimal import Decimal
from types import SimpleNamespace

from hotel_pms.compta import totaux_sejour
from hotel_pms.format import euro


def _ligne(prix, remise="0", taxe="0"):
    return SimpleNamespace(prix_ttc=Decimal(prix), remise_pct=Decimal(remise), taxe_sejour=Decimal(taxe))


def _reglement(montant):
    return SimpleNamespace(montant=Decimal(montant))


def test_totaux_fiche_monnier():
    totaux = totaux_sejour([_ligne("61.20", taxe="4.00")], [_reglement("61.20"), _reglement("4.00")])
    assert totaux.total_ttc == Decimal("61.20")
    assert totaux.total_ht == Decimal("55.64")
    assert totaux.total_tva == Decimal("5.56")
    assert totaux.total_taxe == Decimal("4.00")
    assert totaux.total_general == Decimal("65.20")
    assert totaux.total_paye == Decimal("65.20")
    assert totaux.reste == Decimal("0.00")


def test_remise_puis_tva():
    totaux = totaux_sejour([_ligne("100", remise="10")], [])
    assert totaux.total_ttc == Decimal("90.00")
    assert totaux.total_ht == Decimal("81.82")
    assert totaux.total_tva == Decimal("8.18")
    assert totaux.reste == Decimal("90.00")


def test_euro():
    assert euro(Decimal("61.20")) == "61,20"
    assert euro(Decimal("1234.5")) == "1\u202f234,50"
    assert euro(Decimal("-4")) == "-4,00"
