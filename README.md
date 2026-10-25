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

## Lancer Ma Gouvernante

Ma Gouvernante est une deuxième application, dans `src/ma_gouvernante`. Elle surveille le ménage des chambres. Elle lit la même variable `DATABASE_URL` que Ma Réceptionniste, et donc la même base. Les chambres et les comptes sont ceux de `ma_receptionniste.models`. Au premier démarrage, l'application ajoute la colonne `user.role` (valeur `receptionniste` pour un compte déjà présent), puis les tables `menage` et `historique_menage`.

Les deux serveurs utilisent des ports et des cookies de session différents. Vous pouvez les lancer ensemble, dans deux terminaux.

```bash
uv run python main.py                 # Ma Réceptionniste, http://127.0.0.1:8080
uv run python main_gouvernante.py     # Ma Gouvernante, http://127.0.0.1:8081
```

Sans rechargement auto : `uv run ma-gouvernante`. Le port de Ma Gouvernante est `GOUVERNANTE_PORT`, puis `PORT`, puis `8081`.

Trois comptes sont créés s'ils n'existent pas. Le mot de passe est `panorama`.

| Email | Rôle |
| --- | --- |
| `admin@hotel-panorama.fr` | Admin |
| `reception@hotel-panorama.fr` | Réceptionniste |
| `femme@hotel-panorama.fr` | Femme de chambre |

Si l'email existe déjà, le mot de passe et le rôle restent ceux de la base. C'est le cas de `reception@hotel-panorama.fr` après `scripts/donnees_exemple.py`, dont le mot de passe est aussi `panorama`. L'inscription publique crée uniquement une femme de chambre.

Le test d'interface (`tests/test_fiche_ui.py`) utilise la fixture `User` de NiceGUI, sans navigateur. `pyproject.toml` charge le plugin (`-p nicegui.testing.user_plugin`) et désigne `main.py` comme fichier principal.

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
| `HOST`         | `127.0.0.1`                       |
| `PORT`         | `8080`                            |
| `TAXE_SEJOUR_CENTIMES` | `200` : taxe de séjour par adulte et par nuit, en centimes. Les enfants en sont exonérés. |

## Structure

```
main.py                       point d'entrée de dev (reload)
main_gouvernante.py           point d'entrée de dev de Ma Gouvernante
scripts/
  donnees_exemple.py          base de démonstration, relançable
src/ma_receptionniste/
  __init__.py                 main() : thème, pages, démarrage NiceGUI
  auth.py                     hash des mots de passe, inscription, login, middleware
  db.py                       engine, création des tables, ajout des colonnes manquantes, sessions
  models.py                   modèles SQLModel
  sejours.py                  enregistrer_sejour : seule écriture d'un séjour, contrôle des chevauchements
  facturation.py              nuits, montants, taxe de séjour, totaux, format_euros
  consultations.py            lectures prêtes à afficher : planning, listes, fiche_sejour, statut affiché
  saisie.py                   écritures journalisées : fiche, lignes, consommations, règlements, facture
  pages/                      paquet des pages NiceGUI
    theme.py                  palette, police, props par défaut, formats de date
    layout.py                 page(actif, titre) : menu latéral et barre de titre
    auth_pages.py             /login et /register
    planning.py               /  (grille de la semaine)
    reservations.py           /reservations
    fiche.py                  /reservations/{id} (fiche séjour)
    clients.py                /clients
    chambres.py               /chambres
src/ma_gouvernante/
  __init__.py                 main() : thème, pages, démarrage sur le port 8081
  menage.py                   liste du jour, statuts, historique, droits
  comptes.py                  comptes de démonstration, sans écraser un email existant
  pages/                      login, ménage du jour, historique, chambres
tests/
```

Toutes les pages sauf `/login` et `/register` exigent d'être connecté (voir `PUBLIC_ROUTES` dans `auth.py`).

Les montants sont stockés en centimes entiers et affichés par `format_euros` (`13764` donne `137,64 €`).

## Évolution du schéma

Au démarrage, `create_db_and_tables` crée les tables absentes avec `SQLModel.metadata.create_all`. Il appelle ensuite `ajouter_colonnes_manquantes`, qui ajoute par `ALTER TABLE … ADD COLUMN` les colonnes du modèle absentes d'une table existante. Une nouvelle colonne doit donc être nullable ou avoir un `server_default`. Sinon le démarrage s'arrête sur `ColonneNonAjoutable` avant toute modification. Les renommages, les suppressions et les changements de type de colonne ne sont pas gérés. Ils demanderont Alembic.
