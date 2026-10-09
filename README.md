# eval-usecase-marketing

Projet d’évaluation consacré au ciblage d’une campagne bancaire de dépôt à terme à partir du jeu de données Bank Marketing. Il couvre l’analyse des données, la modélisation, le classement des clients et le suivi des campagnes.

L’objectif métier fixé est de retrouver au moins **80 % des souscripteurs en sélectionnant les 50 % de clients les mieux classés**.

## Notebooks et organisation

| Fichier ou dossier | Contenu |
|---|---|
| [cas_usage_bank_marketing.ipynb](cas_usage_bank_marketing.ipynb) | Analyse exploratoire, préparation, comparaison des modèles et choix de la solution |
| [journal-de-bord.ipynb](journal-de-bord.ipynb) | Journal de bord du projet |
| [rendu_certif.ipynb](rendu_certif.ipynb) | Notebook de rendu réunissant le cas d’usage et le journal de bord |
| `data/` | Données historiques, dont `bank-additional-full.csv` |
| `training/` | Pipeline, entraînement initial et réentraînement des candidats |
| `models/` | Pipeline sauvegardé et métadonnées du modèle |
| `api/` et `frontend/` | API FastAPI et interface web |
| `evaluation/` | Référence historique gelée et golden run |
| `monitoring/`, `prometheus/` et `grafana/` | Suivi des campagnes, dérive des données et tableaux de bord |
| `tests/` | Tests de l’API, du classement, des retours de campagne et de l’évaluation |

## Modèle retenu

Le scénario S5 utilise une régression logistique avec pondération des classes, standardisation des variables numériques et encodage des catégories. Les neuf variables utilisées sont :

- Numériques : `cons.conf.idx`, `cons.price.idx`, `emp.var.rate`, `previous`.
- Catégorielles : `contact`, `default`, `housing`, `loan`, `poutcome`.

La cible `y` indique la souscription : `yes` vaut 1 et `no` vaut 0.

Les résultats enregistrés dans [models/pipeline.json](models/pipeline.json) pour la version `1.0.0` sont :

| Indicateur sur le jeu de test | Valeur |
|---|---:|
| Rappel dans le top 25 % | 66,70 % |
| Rappel dans le top 30 % | 72,09 % |
| Rappel dans le top 50 % | 82,33 % |
| Rappel dans le top 75 % | 91,92 % |
| ROC AUC | 0,7910 |

Le score sert à ordonner les clients. L’interface affiche également le taux de souscription observé dans la tranche correspondante du test historique.

## Lancement avec Docker

Prérequis : Docker et Docker Compose. Depuis la racine du dépôt :

```bash
touch mlflow.db
docker compose up -d --build
```

`touch mlflow.db` crée la base MLflow, absente du dépôt. Sans elle, Docker crée un dossier à sa place et MLflow ne démarre pas.

Le modèle sauvegardé dans `models/` est chargé au démarrage.

| Service | Adresse |
|---|---|
| Interface de ciblage | http://localhost:8000 |
| Documentation interactive de l’API | http://localhost:8000/docs |
| État de l’API et version du modèle | http://localhost:8000/health |
| MLflow | http://localhost:5000 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3001/d/bank-marketing |
| SQLite Web, consultation des données collectées | http://localhost:8080 |

Au premier accès à Grafana, les identifiants sont `admin` / `admin`.

Pour arrêter les services :

```bash
docker compose down
```

## Environnement Python local

Le projet utilise Python 3.12. Les dépendances de l’API sont figées, notamment la version de scikit-learn utilisée pour produire le modèle sauvegardé.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`requirements.txt` installe les dépendances figées de l’API et des tests, puis celles des notebooks.

Ouvrir les notebooks dans un environnement compatible Jupyter et sélectionner le noyau Python de `.venv`.

Pour lancer l’API et son interface web :

```bash
uvicorn api.main:app --reload
```

Les journaux sont écrits dans `logs/api.log`. Les prédictions et les résultats de campagne sont conservés dans `storage/feedback.db` ; la variable `FEEDBACK_DB_PATH` permet de choisir un autre emplacement.

## Utilisation

L’interface permet de scorer un client, de classer un fichier CSV et de renseigner les résultats d’une campagne.

Le fichier à classer doit être encodé en UTF-8, séparé par des virgules ou des points-virgules, et contenir les neuf variables du modèle ainsi que `client_id` et `campaign_id`. Chaque fichier contient une seule campagne, avec un identifiant distinct pour chaque client.

Exemple de fichier :

```csv
client_id;campaign_id;contact;default;housing;loan;poutcome;previous;emp.var.rate;cons.price.idx;cons.conf.idx
C001;campagne-001;cellular;no;yes;no;nonexistent;0;-1.8;92.893;-46.2
C002;campagne-001;telephone;unknown;no;no;failure;1;-1.8;92.893;-46.2
```

Le CSV renvoyé conserve les colonnes reçues et ajoute `score`, `rang`, `tranche`, `taux_reel_tranche` et `hors_historique`.

| Route | Fonction |
|---|---|
| `GET /health` | Vérifier le chargement du modèle |
| `POST /predict` | Scorer un client au format JSON |
| `POST /rank` | Classer un CSV envoyé dans le champ multipart `file` |
| `POST /drift` | Comparer les profils d’un CSV à la référence historique |
| `POST /feedback` | Enregistrer un résultat confirmé avec `client_id`, `campaign_id` et `true_label` (0 ou 1) |
| `POST /campaigns/{campaign_id}/calls` | Enregistrer les clients appelés et leur sélection dans le top 50 % |
| `POST /campaigns/{campaign_id}/close` | Clôturer une campagne et calculer son bilan |
| `GET /metrics` | Exposer les métriques Prometheus |

## Entraînement et suivi

Pour reproduire l’entraînement initial :

```bash
python -m training.train
```

Cette commande remplace `models/pipeline.joblib` et `models/pipeline.json`, puis enregistre un run dans MLflow (`mlflow.db` et `mlruns/`). Elle utilise un découpage stratifié avec 20 % des données pour le test et une graine fixée à 42.

La clôture d’une campagne calcule le taux de souscription du top 50 % parmi les clients dont le résultat est connu. Un réentraînement candidat est déclenché lorsque le volume de nouveaux résultats atteint le seuil prévu ou lorsque ce taux passe sous 18 %. Les candidats sont enregistrés dans `models/candidates/` ; le modèle servi reste en place jusqu’à sa mise à jour manuelle.

Pour comparer un candidat au modèle servi sur la référence gelée :

```bash
python -m scripts.evaluate_model --candidate-dir models/candidates/<identifiant> --champion-dir models
```

Le rapport est écrit dans `reports/evaluation.json`. Les contrôles portent sur le plancher métier de rappel et la non-régression par rapport au modèle précédent et au golden run.

Les modalités de suivi des campagnes, de dérive et de publication sont détaillées dans [monitoring/README.md](monitoring/README.md).

## Vérification et rendu

Exécuter les tests depuis la racine du dépôt :

```bash
pytest -v
```

La CI GitHub Actions exécute les tests et l’évaluation du modèle avant la construction et la publication de l’image Docker sur GHCR lors des pushes sur `main` ou des tags `v*`.

Pour régénérer le notebook de rendu à partir du cas d’usage et du journal de bord :

```bash
python -m scripts.merge_for_certif
```
