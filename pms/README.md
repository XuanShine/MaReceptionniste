# Panorama — PMS réception

Application de réception (planning, séjours, fiche séjour) en **FastAPI**, **HTMX**, **Tailwind** et **SQLModel / SQLite**.

Le projet NiceGUI historique reste à la racine du dépôt. Cette application vit dans `pms/` et ne le modifie pas.

**Python 3.12.3** — Python 3.14 n'est pas installé sur la machine de build. Le projet demande `>=3.12`.

## Lancer

Depuis ce dossier :

```bash
uv run reception
```

Puis ouvrir http://127.0.0.1:8000. La page de connexion s'affiche. Les tables SQLite sont créées au démarrage et le jeu de démonstration est inséré si la base est vide.

Compte de démonstration : `reception` / `reception`.

Le séjour **Monnier Christophe** (partenaire WuBook, chambre 308, 27/10/2026 → 28/10/2026) est prêt à ouvrir depuis **Séjours**. **Détails Séjour** reste inactif dans le menu tant qu'aucune fiche n'a été ouverte. **Abandon** referme la fiche et désactive à nouveau l'entrée.

Avec rechargement automatique :

```bash
uv run uvicorn hotel_pms.main:app --reload --host 127.0.0.1 --port 8000
```

## Base et seed

Fichier par défaut : `pms/hotel_pms.db` (ignoré par git).

```bash
uv run python -m hotel_pms.seed          # crée les tables et sème si vide
uv run python -m hotel_pms.seed --reset  # efface puis réinsère la démo
```

Le mot de passe est stocké en `pbkdf2_sha256` (jamais en clair). La session est un cookie signé (`pms_session`).

| Variable | Défaut |
| --- | --- |
| `PMS_DATABASE_URL` | `sqlite:///…/hotel_pms.db` |
| `PMS_SECRET` | secret de développement, à changer en production |
| `PMS_HOST` | `127.0.0.1` |
| `PMS_PORT` | `8000` |
| `SQL_ECHO` | `1` pour journaliser le SQL |

## Tests

```bash
uv run pytest
uv run ruff check .
```

## Écran séjour

La fiche reprend la structure du dialogue legacy « Séjour » :

- en-tête : nom, client, pays, partenaire, statut (`en_cours` / `traite`), type voiture, facture ;
- bloc droit : Contacts, Notes, Notes internes, Notes tempo, Facturation client ;
- onglets : Réservations, Consommations, Règlements, Modifications, Tickets ;
- règlements : totaux TTC / HT / TVA / taxe / général / reste, et les moyens de paiement.

La TVA hébergement est de 10 %. La taxe de séjour est hors TVA. Pour la démo : 61,20 TTC → 55,64 HT + 5,56 TVA, taxe 4,00, total 65,20, reste 0,00.

## Styles

Tailwind est compilé dans `hotel_pms/static/tailwind.css` (HTMX est aussi vendu dans `static/`). Pour recompiler après un changement de classes :

```bash
tailwindcss -c tailwind.config.js -i hotel_pms/static/input.css -o hotel_pms/static/tailwind.css --minify
```
