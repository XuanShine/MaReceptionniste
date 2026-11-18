"""Contrat du template ODT ; tests autonomes, sans la base de l'application."""

import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_STORED, ZipFile

from scripts.template_facture_odt import DOSSIER, construire_modele, rendre_modele

TEXT_NS = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


@unittest.skipUnless(find_spec("python_odt_template"), "Installer python-odt-template[jinja] pour ces tests optionnels")
class TemplateFactureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dossier = Path(self.temp.name)
        self.modele = construire_modele(self.dossier / "modele.odt")
        self.contexte = json.loads((DOSSIER / "exemple_contexte.json").read_text(encoding="utf-8"))

    def rendre(self, contexte: dict | None = None) -> tuple[Path, str]:
        sortie = rendre_modele(contexte or self.contexte, self.dossier / "rendu.odt", self.modele)
        textes = []
        with ZipFile(sortie) as archive:
            for nom in ("content.xml", "styles.xml"):
                xml = archive.read(nom).decode()
                racine = ET.fromstring(xml)
                self.assertNotIn("{{", xml)
                self.assertNotIn("{%", xml)
                self.assertEqual(racine.findall(f".//{TEXT_NS}text-input"), [])
                textes.append(" ".join(racine.itertext()))
        return sortie, "\n".join(textes)

    def test_archive_odt_et_modele_livre(self) -> None:
        for fichier in (self.modele, DOSSIER / "facture_hotel.odt"):
            with ZipFile(fichier) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(archive.namelist()[0], "mimetype")
                self.assertEqual(archive.getinfo("mimetype").compress_type, ZIP_STORED)
                self.assertEqual(archive.read("mimetype"), b"application/vnd.oasis.opendocument.text")
                for nom in ("content.xml", "styles.xml", "meta.xml", "META-INF/manifest.xml"):
                    ET.fromstring(archive.read(nom))
                ET.fromstring(archive.read("Pictures/paysage.svg"))
                self.assertIn(b'text:description="table-row"', archive.read("content.xml"))

    def test_donnees_facture_existante(self) -> None:
        _, texte = self.rendre()
        for attendu in (
            "Hôtel Panorama",
            "Facturation Alice",
            "Chambre 202",
            "Double Balcon",
            "Petit-Déjeuner",
            "90,90 €",
            "9,10 €",
            "100,00 €",
            "2,00 €",
            "102,00 €",
            "Taxe de séjour",
            "hors base TVA",
            "Échéance : à réception.",
            "Aucun règlement.",
            "EXEMPLE DE MISE EN PAGE",
        ):
            self.assertIn(attendu, texte)

    def test_collections_vides_et_champs_facultatifs(self) -> None:
        contexte = copy.deepcopy(self.contexte)
        contexte["chambres"] = []
        contexte["consommations"] = []
        contexte["ventilations"] = []
        contexte["facture"]["avertissement"] = ""
        _, texte = self.rendre(contexte)
        self.assertIn("Aucune chambre.", texte)
        self.assertIn("Aucune consommation.", texte)
        self.assertNotIn("EXEMPLE DE MISE EN PAGE", texte)
        self.assertNotIn("Base HT", texte)

    def test_boucles_tva_reglements_remplacement_et_echappement(self) -> None:
        contexte = copy.deepcopy(self.contexte)
        contexte["client"]["nom"] = 'Société Été & Fils <Brest> "Accueil"'
        contexte["client"]["complements"] = "SIREN 987654321\nCommande : A&B"
        contexte["facture"]["remplacement"] = "Annule et remplace la facture n° 1 du 16/11/2026"
        contexte["chambres"] *= 3
        contexte["consommations"] *= 2
        contexte["reglements"] = [
            {"date": "16/11/2026", "libelle": "Carte bancaire", "montant": "50,00 €"},
            {"date": "17/11/2026", "libelle": "Remboursement", "montant": "-10,00 €"},
        ]
        contexte["ventilations"].append({"taux": "20 %", "base_ht": "10,00 €", "montant": "2,00 €"})
        contexte["mentions"] = ["Mention spéciale & complément", "Deuxième mention"]
        contexte["conditions"]["penalites"] = "Pénalités B2B : taux indiqué au contrat."
        _, texte = self.rendre(contexte)
        self.assertIn(contexte["client"]["nom"], texte)
        self.assertEqual(texte.count("Double Balcon"), 4)  # Trois lignes et le résumé du séjour.
        self.assertEqual(texte.count("Petit-Déjeuner"), 2)
        for attendu in (
            "Carte bancaire",
            "-10,00 €",
            "20 %",
            "Deuxième mention",
            "Annule et remplace",
            "Pénalités B2B",
        ):
            self.assertIn(attendu, texte)
        self.assertNotIn("Aucun règlement.", texte)

    def test_champ_manquant_refuse(self) -> None:
        from jinja2 import UndefinedError

        del self.contexte["totaux"]["solde"]
        with self.assertRaises(Exception) as capture:
            self.rendre()
        self.assertEqual(type(capture.exception).__name__, "PdfIndisponible")
        self.assertIsInstance(capture.exception.__cause__, UndefinedError)

    @unittest.skipUnless(
        shutil.which("libreoffice") and shutil.which("pdfinfo") and shutil.which("pdftotext"),
        "LibreOffice et Poppler requis pour vérifier les PDF",
    )
    def test_pdf_a4_une_page_et_document_long(self) -> None:
        for long in (False, True):
            with self.subTest(document_long=long):
                contexte = copy.deepcopy(self.contexte)
                if long:
                    contexte["chambres"] = [
                        {**contexte["chambres"][0], "libelle": f"Chambre test {i:03d} — séjour"} for i in range(60)
                    ]
                odt, _ = self.rendre(contexte)
                resultat = subprocess.run(
                    [
                        "libreoffice",
                        f"-env:UserInstallation={(self.dossier / 'profil').as_uri()}",
                        "--headless",
                        "--convert-to",
                        "pdf",
                        "--outdir",
                        str(self.dossier),
                        str(odt),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=90,
                )
                pdf = odt.with_suffix(".pdf")
                self.assertTrue(pdf.is_file(), resultat.stdout + resultat.stderr)
                info = subprocess.run(
                    ["pdfinfo", str(pdf)],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout
                pages = int(next(ligne.split(":")[1] for ligne in info.splitlines() if ligne.startswith("Pages:")))
                self.assertIn("(A4)", info)
                self.assertGreater(pages, 1) if long else self.assertEqual(pages, 1)
                texte_pdf = subprocess.run(
                    ["pdftotext", "-layout", str(pdf), "-"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout
                self.assertIn("102,00", texte_pdf)
                self.assertIn("Échéance : à réception.", texte_pdf)
                if long:
                    self.assertIn("Chambre test 059", texte_pdf)
                    self.assertGreater(texte_pdf.count("DÉSIGNATION / DATES"), 2)


if __name__ == "__main__":
    unittest.main()
