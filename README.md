# Ma Réceptionniste

Application web de réception. FastAPI sert les pages, Jinja et HTMX dessinent l'écran, SQLModel garde les données. Le CSS est un fichier Tailwind compilé, sans CDN.

Ma Gouvernante, dans le même dépôt, reste sur NiceGUI.

## Prérequis

- [uv](https://docs.astral.sh/uv/)

## Installation

```bash
uv sync
```

## Développement

```bash
uv run python main.py      # serveur avec rechargement auto, port 8080
uv run pytest              # tests
uv run ruff check --fix .  # lint
uv run ruff format .       # formatage
```

Sans rechargement auto : `uv run ma-receptionniste`.

L'hôte par défaut est `0.0.0.0`. Le port par défaut est `8080`.

Pour recompiler le CSS après un changement de classes Tailwind :

```bash
npm run build:css
```

## Données de démonstration

Pour remplir une base de démonstration autour de la semaine courante, lancez :

```bash
DATABASE_URL=sqlite:////tmp/demo.db uv run python scripts/donnees_exemple.py
DATABASE_URL=sqlite:////tmp/demo.db uv run ma-receptionniste
```

Le script crée le compte `reception@hotel-panorama.fr` (mot de passe `panorama`), 13 chambres et 16 réservations sur Booking.com, Expedia, Direct et Téléphone. Il est relançable : chaque étape vérifie ce qui existe déjà et n'ajoute que ce qui manque.

## Configuration

Variables d'environnement :

| Variable       | Défaut                            |
| -------------- | --------------------------------- |
| `DATABASE_URL` | `sqlite:///ma_receptionniste.db`  |
| `STORAGE_SECRET` | valeur de dev, **à définir en production** (signe les cookies de session) |
| `SQL_ECHO`     | `0` (mettre `1` pour logger le SQL) |
| `HOST`         | `0.0.0.0`                         |
| `PORT`         | `8080`                            |
| `TAXE_SEJOUR_CENTIMES` | `200` : taxe de séjour par adulte et par nuit, en centimes. Les enfants en sont exonérés. |

## Structure

```
main.py                       point d'entrée de dev (reload)
scripts/
  donnees_exemple.py          base de démonstration, relançable
src/ma_receptionniste/
  __init__.py                 main() : uvicorn
  auth.py                     hash des mots de passe, inscription, authentification
  db.py                       engine, création des tables, ajout des colonnes manquantes, sessions
  models.py                   modèles SQLModel
  sejours.py                  enregistrer_sejour : seule écriture d'un séjour, contrôle des chevauchements
  facturation.py              nuits, montants, taxe de séjour, totaux, format_euros
  consultations.py            lectures prêtes à afficher : planning, listes, fiche_sejour, statut affiché
  saisie.py                   écritures journalisées : fiche, lignes, consommations, règlements, facture
  affichage.py                dates, initiales, saisie d'un montant
  web/                        FastAPI, session, templates Jinja, HTMX
    app.py                    create_app()
    porte.py                  redirection vers /login
    routes_auth.py            /login, /register, /logout
    routes_ecrans.py          planning, dashboard, clients, chambres, réservations
    routes_fiche.py           fiche séjour
    templates/                pages et fragments
    static/                   app.css, htmx.min.js, app.js, police Material Icons
tests/
```

Toutes les pages sauf `/login`, `/register` et `/static` exigent d'être connecté (voir `PUBLIC` dans `web/porte.py`).

Les montants sont stockés en centimes entiers et affichés par `format_euros` (`13764` donne `137,64 €`).

## Évolution du schéma

Au démarrage, `create_db_and_tables` crée les tables absentes avec `SQLModel.metadata.create_all`. Il appelle ensuite `ajouter_colonnes_manquantes`, qui ajoute par `ALTER TABLE … ADD COLUMN` les colonnes du modèle absentes d'une table existante. Une nouvelle colonne doit donc être nullable ou avoir un `server_default`. Sinon le démarrage s'arrête sur `ColonneNonAjoutable` avant toute modification. Les renommages, les suppressions et les changements de type de colonne ne sont pas gérés. Ils demanderont Alembic.
