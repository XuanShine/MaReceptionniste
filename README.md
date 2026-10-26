# Ma Réceptionniste

Deux applications partagent le même métier.

`ma_receptionniste` est l'application NiceGUI d'origine.

`ma_receptionniste2` est la réécriture. SQLModel porte les tables, FastAPI les pages, HTMX et Tailwind le bureau. Le style est volontairement sobre. Papier, encre, filets fins.

Les deux peuvent lire la même base. Le schéma est le même. Le fichier par défaut de la réécriture est distinct, pour ne pas ouvrir celui de NiceGUI par accident.

## Prérequis

- [uv](https://docs.astral.sh/uv/)

## Installation

```bash
uv sync
```

## Développement

```bash
uv run python main.py      # NiceGUI, rechargement auto, http://127.0.0.1:8080
uv run python main2.py     # FastAPI + HTMX, rechargement auto, même port
uv run pytest              # tests
uv run ruff check --fix .  # lint
uv run ruff format .       # formatage
```

Sans rechargement auto : `uv run ma-receptionniste` ou `uv run ma-receptionniste2`.

Le CSS de la réécriture est compilé. Après un changement de classes Tailwind :

```bash
scripts/compiler-tailwind.sh
```

## Configuration

Variables d'environnement :

| Variable       | Défaut                            |
| -------------- | --------------------------------- |
| `DATABASE_URL` | `sqlite:///ma_receptionniste.db` pour NiceGUI, `sqlite:///ma_receptionniste2.db` pour la réécriture |
| `STORAGE_SECRET` | valeur de dev, **à définir en production** (signe les cookies de session) |
| `SQL_ECHO`     | `0` (mettre `1` pour logger le SQL) |
| `HOST`         | `127.0.0.1`                       |
| `PORT`         | `8080`                            |

## Structure

```
main.py                       NiceGUI, rechargement auto
main2.py                      FastAPI, rechargement auto
src/ma_receptionniste/        application NiceGUI
src/ma_receptionniste2/       réécriture FastAPI, SQLModel, HTMX
  models.py                   chambres, clients, réservations, séjours, notes
  sejours.py                  nuits [arrivée, départ) et chevauchement
  templates/                  pages du bureau
  static/app.css              Tailwind compilé
tests/
```

Toutes les pages sauf la connexion et l'inscription exigent un compte.

Les tables sont créées au démarrage. Pour gérer l'évolution du schéma, ajouter Alembic plus tard.

Un séjour du 10 au 12 occupe les nuits du 10 et du 11. Le matin du 12 est libre. Annuler une réservation ne l'efface pas. Ses nuits redeviennent disponibles.
