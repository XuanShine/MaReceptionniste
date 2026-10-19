# Ma Réceptionniste

Application web construite avec [NiceGUI](https://nicegui.io) et [SQLModel](https://sqlmodel.tiangolo.com).

## Prérequis

- [uv](https://docs.astral.sh/uv/)

## Installation

```bash
uv sync
```

## Développement

```bash
uv run python main.py      # serveur avec rechargement auto sur http://127.0.0.1:8080
uv run pytest              # tests
uv run ruff check --fix .  # lint
uv run ruff format .       # formatage
```

Sans rechargement auto : `uv run ma-receptionniste`.

## Configuration

Variables d'environnement :

| Variable       | Défaut                            |
| -------------- | --------------------------------- |
| `DATABASE_URL` | `sqlite:///ma_receptionniste.db`  |
| `STORAGE_SECRET` | valeur de dev, **à définir en production** (signe les cookies de session) |
| `SQL_ECHO`     | `0` (mettre `1` pour logger le SQL) |
| `HOST`         | `127.0.0.1`                       |
| `PORT`         | `8080`                            |

## Structure

```
main.py                       point d'entrée de dev (reload)
src/ma_receptionniste/
  __init__.py                 main() : démarrage NiceGUI
  auth.py                     hash des mots de passe, inscription, login, middleware
  db.py                       engine, création des tables, sessions
  models.py                   modèles SQLModel
  dossier.py                  fiche séjour : état, compte, écriture
  pages/                      pages NiceGUI (planning, fiche, clients, chambres)
tests/
```

Toutes les pages sauf `/login` et `/register` exigent d'être connecté (voir `PUBLIC_ROUTES` dans `auth.py`).

Les tables sont créées au démarrage via `SQLModel.metadata.create_all`. Pour gérer l'évolution du schéma, ajouter Alembic plus tard.
