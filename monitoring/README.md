# Suivi et mises à jour du modèle

Tout le suivi démarre avec `docker compose up -d --build`.

| Interface | Adresse |
|---|---|
| Grafana, tableau de bord provisionné | http://localhost:3001/d/bank-marketing |
| Prometheus, mesures et alertes | http://localhost:9090 |
| MLflow, évaluations et entraînements | http://localhost:5000 |
| SQLite Web, données collectées | http://localhost:8080 |

Grafana utilise `admin` / `admin` au premier accès. Les interfaces de suivi sont liées à localhost.

## Résultats des campagnes

Dans l’interface de l’API :

1. Classer le fichier avec `client_id` et `campaign_id`.
2. Renseigner les résultats confirmés dans « Résultat de campagne ».
3. Cliquer sur « Terminer la campagne » une fois les résultats connus renseignés.

Au clic sur « Terminer la campagne », l’API calcule le taux de souscription des clients du top 50 % dont le résultat est connu. Une fenêtre affiche ce taux, un message s’il est sous 18 %, et les taux annoncés et observés par tranche. Le bilan est enregistré dans SQLite et le taux apparaît dans Grafana. Le rappel global n’est pas calculé sur les seuls clients appelés.

## Dérive des profils

À chaque fichier classé, l’API compare les neuf variables au test historique et enregistre le verdict dans SQLite. Le bouton « Comparer à l’historique » affiche le détail ; Grafana affiche un verdict par variable et par fichier. Le PSI utilise les intervalles entre valeurs distinctes quand les variables en ont peu. Le Chi² n’est interprété que si les effectifs attendus atteignent 5. La dérive des données est un signal pour le diagnostic humain ; l’API ne conclut pas à un concept drift.

Prometheus conserve les séries temporelles ; Grafana affiche six panneaux de suivi. Aucune notification externe n’est configurée.

## Référence et golden run

`evaluation/reference.csv` contient les 8 236 clients du test historique, avec un identifiant d’origine. Ils restent exclus des entraînements. `evaluation/golden.json` enregistre les scores du modèle actuel, les empreintes des artefacts et les tolérances bootstrap. Le script `python -m scripts.freeze_reference` a été exécuté une fois ; il refuse de remplacer une référence existante.

La tolérance de non-régression vaut deux écarts-types du bootstrap (500 tirages, graine 42) : environ 2,44 points de rappel et 1,77 point de ROC AUC. Le plancher métier de rappel de 80 % reste obligatoire. Ces tolérances contrôlent les versions sur la référence historique ; elles ne garantissent pas les résultats d’une nouvelle campagne.

## Contrôle avant publication

Dans l’environnement Python du projet :

```bash
python -m scripts.evaluate_model --candidate-dir models/candidates/1.1.0 --champion-dir models
```

Au push, le job `evaluate-model` récupère le modèle du commit précédent, compare les deux modèles sur la référence, puis compare le candidat au golden run. Une violation ou un fichier de référence modifié bloque la publication. Le rapport et le suivi MLflow sont conservés comme artefacts de CI. Un modèle inchangé est accepté pour permettre les mises à jour du code ; un gain nul ne justifie pas à lui seul un remplacement du modèle.

Le déploiement sur le serveur interne reste manuel, avec vérification de `/health`. Les anciennes images et les anciens artefacts Git permettent le retour à la version précédente.
