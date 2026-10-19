from contextlib import contextmanager

from nicegui import app, ui

from ma_receptionniste.auth import logout_user

LIENS = (
    ("/", "Planning", "calendar_view_week"),
    ("/chambres", "Chambres", "bed"),
    ("/clients", "Clients", "person"),
    ("/reservations", "Réservations", "menu_book"),
)

CSS = """
body {
  background: #efeae2;
  color: #1c1915;
  font-family: "Source Sans 3", "Segoe UI", "Helvetica Neue", sans-serif;
  font-size: 14.5px;
}
.nicegui-content { padding: 0 !important; }
.rail { width: 220px; background: #1c1915; color: #f6f1e8; }
.rail .q-btn { width: 100%; border-radius: 8px; }
.rail .q-btn .q-btn__content { justify-content: flex-start; gap: 10px; font-weight: 500; }
.rail-lien { color: #d9d2c6 !important; }
.rail-lien.actif { background: #1f3d32 !important; color: #fff !important; }
.feuille {
  background: #fbf8f3;
  border: 1px solid #e6dfd2;
  border-radius: 12px;
}
.fiche-haut {
  display: grid;
  grid-template-columns: minmax(280px, 380px) minmax(0, 1fr);
  gap: 12px;
  align-items: stretch;
}
@media (max-width: 960px) {
  .fiche-haut { grid-template-columns: 1fr; }
}
.texte-discret { color: #6e665c; }
.fiche-libelle {
  width: 7.25rem;
  flex: 0 0 7.25rem;
  color: #6e665c;
  font-size: 13px;
}
.fiche-table .q-table thead tr { background: #f6f1e8; }
.fiche-table .q-table th {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #6e665c;
}
.fiche-table .q-table td { font-variant-numeric: tabular-nums; font-size: 13.5px; }
.fiche-table .q-table tbody tr { cursor: pointer; }
.fiche-table .q-table tbody tr:hover { background: #f3f6f4; }
.ligne-ajout { color: #6e665c !important; border: 1px dashed #e0d8c8; border-radius: 8px; }
.barre-actions {
  position: sticky;
  bottom: 0;
  background: #fbf8f3;
  border: 1px solid #e6dfd2;
  border-radius: 12px;
  z-index: 5;
}
.sejour-barre .q-btn__content { justify-content: flex-start; flex-wrap: nowrap; overflow: hidden; }
.sejour-barre .q-btn__content > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.q-field--dense .q-field__control,
.q-field--dense .q-field__marginal { min-height: 36px; }
.q-textarea.q-field--dense .q-field__control { height: auto; min-height: 0; }
.note-zone.q-textarea.q-field--dense .q-field__control { min-height: 220px; }
.q-tab { text-transform: none; min-height: 36px; }
.q-tab__label { font-size: 13px; font-weight: 600; }
.q-panel, .q-tab-panels { background: transparent; }
"""


def theme() -> None:
    ui.colors(
        primary="#1f3d32",
        secondary="#8d6840",
        accent="#c6a15a",
        positive="#2c6b4a",
        negative="#8d3b32",
        warning="#9a6230",
        info="#3c5870",
        dark="#1c1915",
    )
    ui.add_head_html(
        '<link rel="stylesheet" href="https://fonts.bunny.net/css?family=source-sans-3:400,500,600,700&display=swap">'
    )
    ui.add_css(CSS)
    ui.query("body").style("background: #efeae2; color: #1c1915")


def _rail(actif: str) -> None:
    def deconnexion() -> None:
        logout_user()
        ui.navigate.to("/login")

    with ui.column().classes("rail shrink-0 min-h-screen px-3 py-4 justify-between"):
        with ui.column().classes("w-full gap-1"):
            ui.label("PANORAMA").classes("text-xs font-semibold px-2 pt-1").style("letter-spacing: 0.18em")
            ui.label("Réception").classes("text-xs px-2 pb-3").style("color: #b7ad9f")
            for href, label, icone in LIENS:
                actif_classe = "actif" if href == actif else ""
                ui.button(label, icon=icone, on_click=lambda href=href: ui.navigate.to(href)).props(
                    "flat no-caps dense"
                ).classes(f"rail-lien {actif_classe}")
        with ui.column().classes("w-full gap-1"):
            ui.label(app.storage.user.get("nom", "")).classes("text-sm px-2")
            ui.button("Déconnexion", icon="logout", on_click=deconnexion).props("flat no-caps dense").classes(
                "rail-lien"
            )


@contextmanager
def cadre(actif: str):
    theme()
    with ui.row().classes("w-full items-stretch flex-nowrap").style("min-height: 100vh"):
        _rail(actif)
        with ui.column().classes("flex-1 min-w-0 gap-4 p-4"):
            yield


@contextmanager
def ecran_public():
    theme()
    with ui.column().classes("w-full items-center justify-center p-6").style("min-height: 100vh"):
        yield


def titre(texte: str, detail: str | None = None) -> None:
    with ui.column().classes("gap-0"):
        ui.label(texte).classes("text-xl font-semibold leading-tight")
        if detail:
            ui.label(detail).classes("text-sm texte-discret")
