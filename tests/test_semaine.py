from datetime import date

from ma_receptionniste.pages.planning import Semaine


def test_semaine_dun_mercredi() -> None:
    semaine = Semaine(date(2026, 10, 28))

    assert semaine == Semaine(date(2026, 10, 26))
    assert semaine.lundi == date(2026, 10, 26)
    assert semaine.fin == date(2026, 11, 2)
    assert semaine.jours == (
        date(2026, 10, 26),
        date(2026, 10, 27),
        date(2026, 10, 28),
        date(2026, 10, 29),
        date(2026, 10, 30),
        date(2026, 10, 31),
        date(2026, 11, 1),
    )
    assert semaine.precedente().lundi == date(2026, 10, 19)
    assert semaine.suivante() == Semaine(date(2026, 11, 2))
    assert semaine.precedente().suivante() == semaine
    assert semaine.suivante().precedente() == semaine
    assert Semaine(semaine.lundi) == semaine
