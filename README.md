# Ma Réceptionniste

Application web construite avec [NiceGUI](https://nicegui.io) et [SQLModel](https://sqlmodel.tiangolo.com).

## Prérequis

- [uv](https://docs.astral.sh/uv/)
- LibreOffice, pour convertir le modèle de facture en PDF

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
  saisie.py                   écritures journalisées : fiche, occupant, lignes, facture
  pages/                      paquet des pages NiceGUI
    theme.py                  palette, police, props par défaut, formats de date
    layout.py                 page(actif, titre) : menu latéral et barre de titre
    auth_pages.py             /login et /register
    planning.py               /  (grille de la semaine)
    reservations.py           /reservations
    fiche.py                  /reservations/{id} (fiche séjour)
    clients.py                /clients
    chambres.py               /chambres
tests/
```

Toutes les pages sauf `/login` et `/register` exigent d'être connecté (voir `PUBLIC_ROUTES` dans `auth.py`).

Les montants sont stockés en centimes entiers et affichés par `format_euros` (`13764` donne `137,64 €`).

## Import des types de chambres Wubook

Définissez `WUBOOK_TOKEN` et `WUBOOK_LCODE` dans l'environnement (ou dans un fichier `.env`, chargé par le
client Wubook), puis ouvrez **Paramètres → Types de chambre → Mettre à jour les types de chambres de Wubook**.

Après confirmation, le catalogue local est remplacé par `HandlingRooms.fetch_rooms()` :
les chambres standard deviennent des types de chambres, et les chambres virtuelles sont rattachées via `subroom`
(pas via `anchorate`, qui est le parent tarifaire). Les identifiants Wubook, noms/raccourcis, prix par défaut,
prix minimum et indicateurs Channel Manager des types sont importés.

Les chambres physiques et leurs séjours ne sont pas supprimés. Les affectations aux types sont conservées
par `wubook_id` ; celles des types disparus ou sans identifiant Wubook sont retirées.
Un catalogue Wubook vide vide aussi le catalogue local. Un échec de récupération, de validation ou d'insertion
ne modifie aucune donnée locale. Aucun changement n'est envoyé à Wubook.
La création manuelle de types n'est plus proposée dans l'interface.

## Évolution du schéma

Au démarrage, `create_db_and_tables` crée les tables absentes avec `SQLModel.metadata.create_all`. Il appelle ensuite `ajouter_colonnes_manquantes`, qui ajoute par `ALTER TABLE … ADD COLUMN` les colonnes du modèle absentes d'une table existante. Une nouvelle colonne doit donc être nullable ou avoir un `server_default`. Sinon le démarrage s'arrête sur `ColonneNonAjoutable` avant toute modification. Les renommages, les suppressions et les changements de type de colonne ne sont pas gérés. Ils demanderont Alembic.

Exception explicitement prise en charge : les anciennes tables `cellule_virtuelle` et `option_virtuelle`
sont copiées dans `archive_cellule_virtuelle` et `archive_option_virtuelle`, puis retirées dans la même
transaction. Les archives conservent toutes les lignes et formules, sans clés étrangères qui bloqueraient
le remplacement des types de chambres. L'archive des cellules conserve aussi le `wubook_id` et le libellé
du type au moment de la migration. Ces formules ne sont pas converties en prix ni en chambres virtuelles actives.
La migration est idempotente ; un conflit de nom d'archive annule la transaction sans écraser de données.
