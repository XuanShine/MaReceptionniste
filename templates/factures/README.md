# Modèle de facture hôtel

- `facture_hotel.odt` : template A4 éditable dans LibreOffice Writer.
- `exemple_contexte.json` : contrat de données et exemple basé sur `data/factures/facture-1.pdf`.
- `exemple_facture.odt`, `exemple_facture.pdf`, `apercu_facture.png` : démonstration, **pas une facture émise**.

Le dessin original, les titres violets, les tableaux olive, le bloc client lavande
et le récapitulatif reprennent l’esprit de la référence. Les données de Brest du
PDF existant sont utilisées, pas celles de Grasse de l’image. Aucune étoile,
coordonnée de contact ou identité juridique supplémentaire n’est inventée.
La taxe de séjour est séparée de la base TVA, contrairement à l’image de référence.

## Utilisation autonome

Depuis la racine du projet :

```bash
uv run scripts/template_facture_odt.py \
  --contexte templates/factures/exemple_contexte.json \
  --sortie /tmp/facture-exemple.odt

libreoffice -env:UserInstallation=file:///tmp/panorama-conversion \
  --headless --convert-to pdf --outdir /tmp /tmp/facture-exemple.odt
```

Le script déclare sa dépendance `python-odt-template[jinja]==0.5.1` ; `uv run`
l’installe dans un environnement isolé sans modifier les dépendances de l’application.
LibreOffice est nécessaire seulement pour la conversion en PDF.

Intégration Python, après installation de cette même dépendance :

```python
from pathlib import Path
from scripts.template_facture_odt import rendre_modele

rendre_modele(contexte, Path("/tmp/facture.odt"))
```

Le rendu utilise réellement `ODTTemplate` et `get_odt_renderer`, avec
`StrictUndefined` : un champ omis provoque une erreur plutôt qu’une facture
silencieusement incomplète. Les caractères XML et retours à la ligne sont échappés
par la bibliothèque. Ne pas injecter de XML/HTML dans les valeurs.

## Contrat de données

Tous les champs de l’exemple doivent être fournis. Les champs facultatifs sont
des chaînes vides, les collections vides sont `[]`. Les dates, montants et taux
sont des **chaînes déjà formatées** par le moteur métier : le template ne recalcule
ni TVA, ni solde, ni arrondis.

- `hotel` : nom commercial, dénomination, forme/capital, adresse du siège,
  éventuelle adresse de facturation distincte, identifiants et immatriculation/TVA.
  `contact` est un texte libre facultatif pour téléphone, email et site.
- `facture` : numéro, émission, date de prestation ;
  `remplacement` porte, le cas échéant, « Annule et remplace la facture n° … du … » ;
  `avertissement` vaut « Aperçu — facture non émise » pour un aperçu, `""` pour une
  facture définitive. Le bandeau de l’exemple évite de le confondre avec une archive.
- `client` : nom, adresse ; `complements` contient selon le cas l’adresse de
  facturation distincte, le SIREN, la TVA ou la commande.
- `sejour` : référence et période synthétique, sans détail de l’occupation.
- `chambres` et `consommations` : listes de lignes, autant d’éléments que nécessaire.
  Chaque ligne contient libellé, période, quantité, prix unitaire HT, TVA, HT, TTC
  et texte de remise facultatif. Laisser période/remise à `""` si non applicables.
- `reglements` : liste de `{date, libelle, montant}` ; préciser le mode et la nature
  du mouvement dans `libelle`, et le signe du montant pour un remboursement.
- `acomptes` : résumé des acomptes déjà facturés, sans double déduction.
- `ventilations` : une ligne `{taux, base_ht, montant}` par taux de TVA.
- `totaux` : HT, TVA, TTC des prestations, taxe de séjour, total à payer, réglé, solde.
- `conditions` : échéance, escompte, pénalités applicables et mention TVA/exonération.
- `mentions` : liste de mentions supplémentaires, notamment les obligations B2B
  et l’indemnité de recouvrement lorsque applicables.
- `message_remerciement` : texte de courtoisie.

Les en-têtes des tableaux de prestations se répètent sur les pages suivantes.
Les lignes ne sont pas coupées entre deux pages ; le pied contient la pagination.
Les sections vides affichent un message. Les champs facultatifs vides ne créent
pas de paragraphes vides.

## Modifier le modèle

Ouvrir `facture_hotel.odt` dans Writer. Les variables et boucles sont des **champs
de saisie** (`text:text-input`), pas de simples balises Jinja tapées dans le texte.
Préserver les champs de contrôle des boucles et leur portée `table-row` ou
`paragraph`. Les lignes techniques des boucles disparaissent au rendu.

Le dessin vectoriel embarqué est décoratif ; le remplacer par le logo officiel
dans Writer si disponible. Les polices sont Liberation Serif et Liberation Sans.

Pour reconstruire le modèle depuis sa source Python (**écrase les retouches Writer**) :

```bash
uv run scripts/template_facture_odt.py --construire
```

Tests indépendants de l’application et de sa base :

```bash
uv run --no-project --with 'python-odt-template[jinja]==0.5.1' \
  python -m unittest discover -s tests -p test_template_facture_odt.py -v
```

L’application remplit ce modèle depuis les instantanés de facture, puis LibreOffice
produit le PDF. LibreOffice est un prérequis d’exécution. Une archive déjà écrite
n’est pas régénérée. Le modèle seul ne garantit pas la conformité des données
ni ne remplace les obligations de facturation électronique.
