from datetime import date, timedelta

from hotel_pms.lecture import SegmentPlanning, grille_planning


def _jours(debut: date, nombre: int = 14) -> list[date]:
    return [debut + timedelta(days=i) for i in range(nombre)]


def test_sejour_de_plusieurs_nuits_une_cellule():
    grille = grille_planning(
        [SegmentPlanning(1, "Bernard Alain", 201, date(2026, 10, 28), date(2026, 10, 30), True)],
        [201],
        _jours(date(2026, 10, 25)),
    )
    voie = grille[201][0]
    sejours = [cellule for cellule in voie if cellule.sejour_id]
    assert len(sejours) == 1
    assert sejours[0].span == 2
    assert sejours[0].nuits == 2
    assert sejours[0].nom == "Bernard Alain"
    assert sum(cellule.span for cellule in voie) == 14


def test_une_nuit_reste_une_cellule():
    grille = grille_planning(
        [SegmentPlanning(4, "Monnier Christophe", 308, date(2026, 10, 27), date(2026, 10, 28), True)],
        [308],
        _jours(date(2026, 10, 25)),
    )
    sejour = next(cellule for cellule in grille[308][0] if cellule.sejour_id)
    assert sejour.span == 1
    assert sejour.nuits == 1


def test_sejours_successifs_partagent_la_voie():
    grille = grille_planning(
        [
            SegmentPlanning(1, "Martin Sophie", 102, date(2026, 10, 25), date(2026, 10, 27), False),
            SegmentPlanning(2, "Autre", 102, date(2026, 10, 27), date(2026, 10, 29), True),
        ],
        [102],
        _jours(date(2026, 10, 25)),
    )
    assert len(grille[102]) == 1
    assert [cellule.nom for cellule in grille[102][0] if cellule.sejour_id] == ["Martin Sophie", "Autre"]


def test_chevauchement_ouvre_une_seconde_voie():
    grille = grille_planning(
        [
            SegmentPlanning(1, "A", 5, date(2026, 10, 1), date(2026, 10, 4), True),
            SegmentPlanning(2, "B", 5, date(2026, 10, 2), date(2026, 10, 3), True),
        ],
        [5],
        _jours(date(2026, 10, 1), 7),
    )
    assert len(grille[5]) == 2
    assert [(c.nom, c.span) for c in grille[5][0] if c.sejour_id] == [("A", 3)]
    assert [(c.nom, c.span) for c in grille[5][1] if c.sejour_id] == [("B", 1)]
    assert all(sum(c.span for c in voie) == 7 for voie in grille[5])


def test_sejour_coupe_par_la_fenetre_garde_ses_nuits():
    grille = grille_planning(
        [SegmentPlanning(3, "Long", 1, date(2026, 10, 23), date(2026, 10, 27), False)],
        [1],
        _jours(date(2026, 10, 25)),
    )
    bloc = next(cellule for cellule in grille[1][0] if cellule.sejour_id)
    assert bloc.span == 2
    assert bloc.nuits == 4
