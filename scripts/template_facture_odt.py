# /// script
# requires-python = ">=3.12"
# dependencies = ["python-odt-template[jinja]==0.5.1"]
# ///
"""Construction et rendu autonomes du modèle ODT, sans accès à la base métier."""

import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DOSSIER = ROOT / "templates" / "factures"
MODELE = DOSSIER / "facture_hotel.odt"
NS = (
    'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
    'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
    'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" '
    'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
    'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" '
    'xmlns:xlink="http://www.w3.org/1999/xlink" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/"'
)
XML = '<?xml version="1.0" encoding="UTF-8"?>'
VIOLET, OLIVE, ENCRE = "#655174", "#777C55", "#30322F"


def champ(expression: str, description: str = "") -> str:
    """Champs de saisie Writer reconnus par python-odt-template (pas du texte brut)."""
    return f"<text:text-input text:description={quoteattr(description)}>{escape(expression)}</text:text-input>"


def variable(expression: str) -> str:
    return champ("{{ " + expression + " }}")


def p(contenu: str = "", style: str = "Corps") -> str:
    return f'<text:p text:style-name="{style}">{contenu}</text:p>'


def p_optionnel(expression: str, style: str = "Corps") -> str:
    return (
        p(champ("{% if " + expression + " %}", "paragraph"))
        + p(variable(expression), style)
        + p(champ("{% endif %}", "paragraph"))
    )


def cellule(contenu: str, style: str = "Cellule") -> str:
    return f'<table:table-cell table:style-name="{style}" office:value-type="string">{contenu}</table:table-cell>'


def ligne(*cellules: str) -> str:
    return '<table:table-row table:style-name="Ligne">' + "".join(cellules) + "</table:table-row>"


def directive_row(expression: str, colonnes: int) -> str:
    # Le moteur supprime cette ligne entière, et non une partie du XML de la cellule.
    contenu = p(champ("{% " + expression + " %}", "table-row"))
    return ligne(cellule(contenu), *(cellule(p()) for _ in range(colonnes - 1)))


def tableau(nom: str, largeurs: tuple[float, ...], contenu: str) -> str:
    colonnes = "".join(f'<table:table-column table:style-name="Col{largeur:g}"/>' for largeur in largeurs)
    return f'<table:table table:name="{nom}" table:style-name="Tableau">{colonnes}{contenu}</table:table>'


def styles_automatiques() -> str:
    largeurs = (1, 1.3, 2.3, 2.7, 7, 7.4, 7.7, 10.4)
    colonnes = "".join(
        f'<style:style style:name="Col{x:g}" style:family="table-column">'
        f'<style:table-column-properties style:column-width="{x:g}cm"/></style:style>'
        for x in largeurs
    )
    cellules = ""
    for nom, fond, bordure in (
        ("Cellule", "transparent", "none"),
        ("Carte", "#F1EDF3", "none"),
        ("Entete", OLIVE, "none"),
        ("Donnee", "transparent", "0.3pt solid #DEDCD5"),
        ("Total", "#ECE5F1", "none"),
    ):
        cellules += (
            f'<style:style style:name="{nom}" style:family="table-cell">'
            f'<style:table-cell-properties fo:padding="0.16cm" fo:background-color="{fond}" '
            f'fo:border-bottom="{bordure}" style:vertical-align="top"/></style:style>'
        )
    return (
        '<style:style style:name="Tableau" style:family="table">'
        '<style:table-properties style:width="17.4cm" table:align="margins" '
        'fo:margin-bottom="0.18cm"/></style:style>'
        '<style:style style:name="Ligne" style:family="table-row">'
        '<style:table-row-properties fo:keep-together="always"/></style:style>' + colonnes + cellules
    )


def styles_document() -> str:
    def paragraphe(
        nom: str,
        taille: str = "9pt",
        couleur: str = ENCRE,
        *,
        police: str = "Liberation Sans",
        gras: bool = False,
        align: str = "start",
        avant: str = "0cm",
        apres: str = "0.08cm",
        plus: str = "",
    ) -> str:
        return (
            f'<style:style style:name="{nom}" style:family="paragraph">'
            f'<style:paragraph-properties fo:text-align="{align}" fo:margin-top="{avant}" '
            f'fo:margin-bottom="{apres}" fo:line-height="120%" {plus}/>'
            f'<style:text-properties style:font-name="{police}" fo:font-size="{taille}" '
            f'fo:color="{couleur}" fo:font-weight="{"bold" if gras else "normal"}"/>'
            "</style:style>"
        )

    styles = "".join(
        (
            paragraphe("Corps"),
            paragraphe("Petit", "8pt"),
            paragraphe("Discret", "7.5pt", "#76756D"),
            paragraphe("Hotel", "24pt", police="Liberation Serif", apres="0.16cm"),
            paragraphe("Titre", "29pt", VIOLET, police="Liberation Serif", align="end", apres="0.2cm"),
            paragraphe("Droite", align="end"),
            paragraphe("Chiffre", "8.5pt", align="end"),
            paragraphe("Libelle", "7.5pt", VIOLET, gras=True, apres="0.13cm"),
            paragraphe(
                "Section", "10pt", VIOLET, gras=True, avant="0.25cm", apres="0.17cm", plus='fo:keep-with-next="always"'
            ),
            paragraphe("Colonne", "7pt", "#FFFFFF", gras=True, apres="0cm"),
            paragraphe("ColonneDroite", "7pt", "#FFFFFF", gras=True, align="end", apres="0cm"),
            paragraphe("Solde", "18pt", VIOLET, police="Liberation Serif", gras=True, align="end"),
            paragraphe("SoldeLibelle", "12pt", VIOLET, police="Liberation Serif"),
            paragraphe("Merci", "9pt", VIOLET, avant="0.25cm"),
            paragraphe("Pied", "7pt", "#76756D", align="center"),
            paragraphe(
                "Trait",
                "7pt",
                VIOLET,
                apres="0.15cm",
                plus=f'fo:border-top="0.6pt solid {VIOLET}" fo:padding-top="0.14cm"',
            ),
            paragraphe("Alerte", "9pt", VIOLET, gras=True, avant="0.1cm", apres="0.2cm"),
        )
    )
    pied = (
        p(variable("hotel.nom_commercial") + " · " + variable("hotel.adresse_siege"), "Pied")
        + p_optionnel("hotel.contact", "Pied")
        + p(
            'Page <text:page-number text:select-page="current">1</text:page-number>'
            " / <text:page-count>1</text:page-count>",
            "Pied",
        )
    )
    return (
        XML + f'<office:document-styles {NS} office:version="1.2">'
        "<office:font-face-decls>"
        '<style:font-face style:name="Liberation Sans" svg:font-family="Liberation Sans"/>'
        '<style:font-face style:name="Liberation Serif" svg:font-family="Liberation Serif"/>'
        "</office:font-face-decls><office:styles>"
        '<style:default-style style:family="paragraph"><style:paragraph-properties '
        'fo:orphans="2" fo:widows="2"/><style:text-properties style:font-name="Liberation Sans" '
        'fo:font-size="9pt" fo:language="fr" fo:country="FR"/></style:default-style>'
        + styles
        + "</office:styles><office:automatic-styles>"
        '<style:page-layout style:name="A4"><style:page-layout-properties '
        'fo:page-width="21cm" fo:page-height="29.7cm" style:print-orientation="portrait" '
        'fo:margin-top="1.25cm" fo:margin-bottom="1.2cm" fo:margin-left="1.8cm" fo:margin-right="1.8cm" '
        'fo:background-color="#FFFEFA"/>'
        '<style:footer-style><style:header-footer-properties fo:min-height="0.9cm" '
        'fo:margin-top="0.3cm" fo:border-top="0.6pt solid #655174" fo:padding-top="0.15cm"/>'
        "</style:footer-style></style:page-layout></office:automatic-styles>"
        '<office:master-styles><style:master-page style:name="Standard" style:page-layout-name="A4">'
        "<style:footer>" + pied + "</style:footer></style:master-page></office:master-styles>"
        "</office:document-styles>"
    )


def tableau_prestations(collection: str, nom: str, vide: str) -> str:
    entetes = ("DÉSIGNATION / DATES", "QTÉ", "P.U. HT", "TVA", "HT", "TTC")
    entete = ligne(*(cellule(p(t, "Colonne" if i == 0 else "ColonneDroite"), "Entete") for i, t in enumerate(entetes)))
    description = p(variable("l.libelle")) + p_optionnel("l.periode", "Discret") + p_optionnel("l.remise", "Discret")
    valeurs = (
        description,
        *(p(variable(f"l.{cle}"), "Chiffre") for cle in ("quantite", "prix_unitaire_ht", "tva", "ht", "ttc")),
    )
    corps = (
        directive_row(f"for l in {collection}", 6)
        + ligne(*(cellule(valeur, "Donnee") for valeur in valeurs))
        + directive_row("else", 6)
        + ligne(cellule(p(vide, "Discret"), "Donnee"), *(cellule(p(), "Donnee") for _ in range(5)))
        + directive_row("endfor", 6)
    )
    return tableau(
        nom, (7.4, 1, 2.3, 1.3, 2.7, 2.7), "<table:table-header-rows>" + entete + "</table:table-header-rows>" + corps
    )


def contenu_document() -> str:
    logo = (
        '<draw:frame draw:name="Paysage" text:anchor-type="as-char" svg:width="5.3cm" svg:height="1.45cm">'
        '<draw:image xlink:href="Pictures/paysage.svg" xlink:type="simple" '
        'xlink:show="embed" xlink:actuate="onLoad"/></draw:frame>'
    )
    hotel = (
        p(logo)
        + p(variable("hotel.nom_commercial"), "Hotel")
        + p(variable("hotel.denomination"), "Petit")
        + p(variable("hotel.forme_capital"), "Petit")
        + p(variable("hotel.adresse_siege"), "Petit")
        + p_optionnel("hotel.adresse_facturation", "Petit")
        + p(variable("hotel.identifiants"), "Petit")
        + p(variable("hotel.immatriculation_tva"), "Petit")
    )
    facture = (
        p("FACTURE", "Titre")
        + p("N° " + variable("facture.numero"), "Droite")
        + p("Émise le " + variable("facture.date_emission"), "Droite")
        + p("Prestation du " + variable("facture.date_prestation"), "Droite")
        + p_optionnel("facture.remplacement", "Alerte")
    )
    client = (
        p("FACTURÉ À", "Libelle")
        + p(variable("client.nom"))
        + p(variable("client.adresse"), "Petit")
        + p_optionnel("client.complements", "Petit")
    )
    sejour = (
        p("INFORMATIONS DU SÉJOUR", "Libelle")
        + p(variable("sejour.reference"), "Petit")
        + p(variable("sejour.periode"), "Petit")
    )
    reglements = (
        directive_row("for r in reglements", 3)
        + ligne(
            cellule(p(variable("r.date"), "Petit"), "Donnee"),
            cellule(p(variable("r.libelle"), "Petit"), "Donnee"),
            cellule(p(variable("r.montant"), "Chiffre"), "Donnee"),
        )
        + directive_row("else", 3)
        + ligne(
            '<table:table-cell table:number-columns-spanned="3">'
            + p("Aucun règlement.", "Petit")
            + "</table:table-cell>"
            "<table:covered-table-cell/><table:covered-table-cell/>"
        )
        + directive_row("endfor", 3)
    )
    tva = (
        p("DÉTAIL DE LA TVA", "Libelle")
        + p(champ("{% for v in ventilations %}", "paragraph"))
        + p(
            "Base HT " + variable("v.taux") + " : " + variable("v.base_ht") + "  ·  TVA : " + variable("v.montant"),
            "Petit",
        )
        + p(champ("{% endfor %}", "paragraph"))
        + p_optionnel("conditions.mention_tva", "Petit")
        + p(variable("message_remerciement"), "Merci")
    )
    totaux = ""
    for libelle, cle in (
        ("Total HT", "ht"),
        ("Total TVA", "tva"),
        ("TTC des prestations", "prestations_ttc"),
        ("Taxe de séjour · hors base TVA", "taxe_sejour"),
        ("Total à payer", "a_payer"),
        ("Montant réglé", "regle"),
    ):
        totaux += p(escape(libelle) + " : " + variable(f"totaux.{cle}"), "Droite")
    totaux += p("SOLDE À PAYER", "SoldeLibelle") + p(variable("totaux.solde"), "Solde")
    corps = (
        p_optionnel("facture.avertissement", "Alerte")
        + tableau("Identite", (10.4, 7), ligne(cellule(hotel), cellule(facture)))
        + tableau("Sejour", (10.4, 7), ligne(cellule(client, "Carte"), cellule(sejour, "Carte")))
        + p("01  /  CHAMBRES", "Section")
        + tableau_prestations("chambres", "Chambres", "Aucune chambre.")
        + p("02  /  CONSOMMATIONS", "Section")
        + tableau_prestations("consommations", "Consommations", "Aucune consommation.")
        + p("03  /  RÈGLEMENTS", "Section")
        + tableau("Reglements", (2.3, 7.4, 7.7), reglements)
        + p(variable("acomptes"), "Discret")
        + p("", "Trait")
        + tableau("Recapitulatif", (10.4, 7), ligne(cellule(tva), cellule(totaux, "Total")))
        + p("CONDITIONS DE RÈGLEMENT", "Libelle")
        + p(variable("conditions.echeance"), "Petit")
        + p(variable("conditions.escompte"), "Petit")
        + p_optionnel("conditions.penalites", "Petit")
        + p(champ("{% for mention in mentions %}", "paragraph"))
        + p(variable("mention"), "Petit")
        + p(champ("{% endfor %}", "paragraph"))
    )
    return (
        XML + f'<office:document-content {NS} office:version="1.2">'
        "<office:automatic-styles>" + styles_automatiques() + "</office:automatic-styles>"
        "<office:body><office:text>" + corps + "</office:text></office:body></office:document-content>"
    )


def construire_modele(destination: Path = MODELE) -> Path:
    """Produit un ODT A4 éditable dans Writer, avec des boucles sur lignes de tableau."""
    paysage = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 530 145">
      <g fill="none" stroke="{VIOLET}" stroke-width="1.8" stroke-linecap="round">
        <path d="M15 112 Q90 38 168 90 Q252 15 346 90 Q426 45 515 110"/>
        <path d="M25 119 Q134 77 247 112 T505 121"/>
        <path d="M110 82 A48 48 0 0 1 206 70"/>
        <path d="M153 22 V10 M122 30 L116 19 M185 24 L190 12 M99 46 L87 39 M211 39 L222 30"/>
        <path d="M245 114 V79 L270 62 L296 79 V114 M250 80 H291 M264 114 V94 H277 V114"/>
        <path d="M314 113 V70 L326 48 L338 70 V114 M321 83 H331 M321 94 H331"/>
      </g>
      <g fill="none" stroke="{OLIVE}" stroke-width="2">
        <path d="M43 123 V73 M43 107 Q15 91 36 80 M43 100 Q70 84 49 70"/>
        <path d="M463 122 V68 M463 106 Q435 84 455 73 M463 95 Q489 77 469 64"/>
        <path d="M65 130 Q265 138 475 130"/>
      </g></svg>"""
    manifest = (
        XML + '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" '
        'manifest:version="1.2">'
        '<manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>'
        + "".join(
            f'<manifest:file-entry manifest:full-path="{nom}" manifest:media-type="{mime}"/>'
            for nom, mime in (
                ("content.xml", "text/xml"),
                ("styles.xml", "text/xml"),
                ("meta.xml", "text/xml"),
                ("Pictures/paysage.svg", "image/svg+xml"),
            )
        )
        + "</manifest:manifest>"
    )
    meta = (
        XML + f'<office:document-meta {NS} office:version="1.2"><office:meta>'
        "<dc:title>Facture hôtel — modèle violet et olive</dc:title>"
        "<dc:description>Template python-odt-template ; montants fournis par le moteur métier.</dc:description>"
        "</office:meta></office:document-meta>"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=ZIP_STORED)
        for nom, contenu in (
            ("content.xml", contenu_document()),
            ("styles.xml", styles_document()),
            ("meta.xml", meta),
            ("META-INF/manifest.xml", manifest),
            ("Pictures/paysage.svg", paysage),
        ):
            archive.writestr(nom, contenu)
    return destination


def rendre_modele(contexte: dict, destination: Path, modele: Path = MODELE) -> Path:
    """Même rendu que l'application. Ne calcule, n'émet et ne remplace aucune facture."""
    from importlib.util import module_from_spec, spec_from_file_location

    chemin = ROOT / "src" / "ma_receptionniste" / "facturation_odt.py"
    spec = spec_from_file_location("facturation_odt_autonome", chemin)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Rendu introuvable : {chemin}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.rendre_odt(contexte, destination, modele)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--construire", action="store_true", help="Reconstruire le template ODT.")
    parser.add_argument("--contexte", type=Path, help="JSON contenant toutes les valeurs à afficher.")
    parser.add_argument("--sortie", type=Path, default=DOSSIER / "exemple_facture.odt")
    args = parser.parse_args()
    if args.construire:
        print(construire_modele())
    if args.contexte:
        contexte = json.loads(args.contexte.read_text(encoding="utf-8"))
        print(rendre_modele(contexte, args.sortie))
    if not args.construire and not args.contexte:
        parser.print_help()


if __name__ == "__main__":
    main()
