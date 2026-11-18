from datetime import date, timedelta

from nicegui import background_tasks, run, ui

from ma_receptionniste.disponibilites import disponibilites_par_type, matrice_disponibilites
from ma_receptionniste.pages.layout import page


def _charger_disponibilites(debut: date, fin: date) -> dict:
    return disponibilites_par_type(matrice_disponibilites(debut, fin))


@ui.page("/disponibilites")
def disponibilites() -> None:
    aujourd_hui = date.today()

    async def afficher() -> None:
        if not bouton.enabled:
            return
        try:
            debut = date.fromisoformat(date_debut.value or "")
            fin = date.fromisoformat(date_fin.value or "")
        except ValueError:
            ui.notify("Renseignez deux dates valides", type="warning")
            return
        if fin <= debut:
            ui.notify("La date de fin doit être après la date de début", type="warning")
            return

        bouton.disable()
        chargement.set_visibility(True)
        try:
            resultat = await run.io_bound(_charger_disponibilites, debut, fin)
            if resultat is None:
                return
            tableau.columns = [
                {"name": "date", "label": "Date", "field": "date", "align": "left"},
                *[
                    {
                        "name": f"type_{type_['id']}",
                        "label": type_["libelle"],
                        "field": f"type_{type_['id']}",
                        "align": "center",
                    }
                    for type_ in resultat["types"]
                ],
            ]
            tableau.rows = [
                {
                    "id": jour.isoformat(),
                    "date": jour.strftime("%d/%m/%Y"),
                    **{
                        f"type_{type_['id']}": valeurs[index]
                        for type_, valeurs in zip(resultat["types"], resultat["valeurs"], strict=True)
                    },
                }
                for index, jour in enumerate(resultat["dates"])
            ]
            tableau.update()
            tableau.set_visibility(bool(resultat["types"]))
            vide.set_visibility(not resultat["types"])
            resume.set_text(f"Du {debut:%d/%m/%Y} au {fin:%d/%m/%Y} (fin exclue) · {len(resultat['dates'])} nuits")
        finally:
            chargement.set_visibility(False)
            bouton.enable()

    with page("/disponibilites", "Disponibilités"):
        with ui.card().props("flat bordered").classes("w-full rounded-lg gap-3"):
            with ui.row().classes("w-full items-end gap-3"):
                date_debut = (
                    ui.input("Date de début", value=aujourd_hui.isoformat())
                    .props("type=date")
                    .mark("disponibilites-debut")
                )
                date_fin = (
                    ui.input("Date de fin (exclue)", value=(aujourd_hui + timedelta(days=365)).isoformat())
                    .props("type=date")
                    .mark("disponibilites-fin")
                )
                bouton = ui.button("Afficher", icon="search", on_click=afficher)
                chargement = ui.spinner(size="sm")
                chargement.set_visibility(False)
            ui.label("Nombre de chambres disponibles par type et par nuit.").classes("text-sm text-ardoise")
        resume = ui.label().classes("text-sm text-ardoise").mark("disponibilites-periode")
        vide = ui.label("Aucun type de chambre configuré.").classes("text-sm text-ardoise")
        vide.set_visibility(False)
        tableau = (
            ui.table(columns=[], rows=[], row_key="id", pagination=0)
            .props("flat bordered dense hide-bottom")
            .classes("w-full max-h-[65vh] overflow-auto")
            .mark("tableau-disponibilites")
        )
        tableau.set_visibility(False)
        background_tasks.create(afficher(), context=ui.context.client)
