


# CONTEXTE

## Objectif Métier

Créer un modèle d’IA pour cibler les clients d’une banque dans le cadre d’une campagne de démarchage téléphonique.  
Prédire quels clients sont les plus susceptibles de souscrire un contrat pour un produit d’épargne.  

Important de bien cibler les clients (appeler les clients les plus susceptibles de souscrire) parce que 
- les campagnes sont chères pour la banque (plate-forme d'appel, temps des consiellers bancaires)
- un appel mal ciblé nuit à l’activité commerciale de la banque (saturation d'appels non pertinents, dégradation de la relation commerciale)

## Coût des Erreurs et Priorité au Rappel

Coût d'un FAUX POSITIF (appeler un client qui ne souscrit pas) :
ça coûte à la banque (coût de l'appel et nuisance à l'acivité commerciale)
mais finalement c'est pas tant que ça (un appel et une petite frustration )
== ça justifie un ciblage (on ne contacte pas tout le monde)
mais on peut se permettre une grande part de faux positif 

Coût d'un FAUX NÉGATIF (ne pas appeler un client qui aurait souscri) : 
manque à gagner financier pour la banque (les bénéfices que la banque aurait gagnés avec la souscription d'un contrat)
qu'on imagine élevé 

DONC : 
- faux positif pas si coûteux que ça finalement (mais il faut quand même cibler)
- faux négatif coûteux financièrement 
- pour faire un véritable arbitrage, il faudrait connaître ce que rapporte en moyenne un contrat souscrit
  et le comparer avec le coût des appels (coût financier évaluable, pas la dégradation de la relation client)
==  ON PRIVILÉGIE LE RAPPEL POUR LIMITER LES FAUX NÉGATIFS
    ON ACCEPTE DAVANTAGE DE FAUX POSTIIFS 

le ciblage permet de réduire le coût d’acquisition client 
en limitant les appels qui n’aboutissent pas à une souscription 
tant que la marge attendue d’un client acquis dépasse son coût d’acquisition
la campagne reste rentable (le but de la banque)



# EXPLORATION ET PRÉPARTION DES DONNÉES (EDA)

> Doc : [`aide_memoire_M1.pdf`](docs/aide_memoire_M1.pdf) — workflow en 7 étapes, règle « on n'apprend que sur le train », tableau des métriques, fuite de données.


## La Cible

CIBLE : est-ce que le client souscrira ou non
==  classifictaion binaire (oui/non)


## Les Variables Explicatives (20)

dans le pdf
mais aussi dans la doc sur hugging face  



## Vérification de la Qualité des Données

s'assurer de la bonne qualité des données avant toute manipulation


## Préparation Raisonnée du Jeu de Données

# MODÉLISATION ET ÉVALUATION

> Doc : [`aide_memoire_M1.pdf`](docs/aide_memoire_M1.pdf) — workflow en 7 étapes, règle « on n'apprend que sur le train », tableau des métriques, fuite de données.

## Tester et Comparer Plusieurs Familles de Modèles

tester plusieurs familles de modèles : 
- une régression logistique comme référence,
- un arbre de décision
- une forêt aléatoire

comparer leurs performances avec des métriques appropriées
précision, rappel, F1-score, ROC-AUC, matrice de confusion 

- Modèle fiable : vérifier la stabilité des performances par validation croisée.
- Vérifier que le modèle reste fiable sur de nouveaux clients, même si les données sont imparfaites ou légèrement différentes de celles utilisées pour l’entraînement.

ATTENTION : 
la classe « oui » est nettement minoritaire (environ 11 % des observations) 
donc on peut avoir une accuracy de 89% avec un mauvais modèle 

et documenter toujours le choix des métriques 
et l'importance qu'on leur accorde 
et pourquoi on privilégie une métrique plutôt que l'autre 
== faire le lien avec le contexte métier

=> lier à la question de l'EXPLICABILITÉ 
la solution doit être explicable 
donc on veut un modèle aussi simple que possible

dans quelle mesure l'explicabilité est importante ? 

réfléchir à l'impact que va avoir la prédiction 
dans notre cas c'est juste un appel donc c'est minime (?)
et on est un acteur privé, pas l'État 
réfléchir à d'autres arguments 


## Analyse Comparée de Scénarios

### But

comparer les performances 
selon différents jeux de variables 
pour objectiver l'impact de variables discutables : 
- celles qui posent un problème de fuite d'information (leakage) 
- celles qui posent un problème éthique 

voir si la performance chute de beaucoup si on se passe de certaines varibles 
== évaluer le coût de la conformité éthique ou anti-fuite d'info

L'objectif est de documenter et commenter 
l'impact de chaque scénario sur les performances des modèles
puis d'argumenter le choix final du modèle et des variables à retenir dans un contexte réel 
en tenant compte des enjeux éthiques, légaux et de robustesse

### Scénario 1 : toutes les variables disponibles

on utilise l'ensemble des colonnes
y compris la durée du dernier appel (duration)

== sert de performance de référence

### Scénario 2 : sans la variable duration

Retirer la variable duration (durée du dernier appel) 
et comparer à la référence 
et commenter l'écart de performance observé entre les scénarios 1 et 2
 

À interroger : 
à quel moment la durée d'un appel est-elle réellement connue ?
Si elle n'est disponible qu'une fois l'appel terminé
peut-on légitimement l'utiliser pour décider, en amont, qui appeler ?

à clarifier : 
=> c'est pas une histoire de rappel ? 
donc on se base sur des anciennes campagnes pour décider des nouelles campagnes 
les données ne sont pas dispo pour tous les clients ? 

### Scénario 3 : sans variables sensibles + RGPD & données personnelles

Retier en plus (aussi duration) 
les variables que vous jugez éthiquement discutables pour un ciblage commercial 
(par exemple l'âge, la profession, la situation familiale, le niveau d'éducation) 
en justifiant chaque retrait

pour cibler
on utilise : 
- le profil du client 
- l'historique des contacts 

donc on utilise des données personnelles (âge, profession, situation familiale, niveau d'éducation)
ça pose des questions : 
- d'équité (discriminations possibles)
- de conformité RGPD 
- de pratique commerciale acceptable
== il faut respecter les contraintes réglementaires et éthique

pas acceptable : 
- une solution discriminante (même si performante)
- une solution opaque

Cette partie évalue la capacité de raisonnement
Appuyer les réponses sur des observations concrètes
issues de vos données et de vos résultats 

Protection des données personnelles (RGPD)
- Qualifiez la nature des données mobilisées : lesquelles sont des données personnelles ?
- Certaines relèvent-elles de catégories particulières au sens de l'article 9 du RGPD ? 
- Quelle base légale pourrait justifier ce traitement de démarchage ? Quelles obligations en découlent (information des personnes, minimisation des données, durée de conservation) ?

BIAIS, ÉQUITÉ & DISCRIMINATIONS
Mesurer la performance de votre modèle par sous-groupe (par exemple par tranche d'âge ou par profession)
=> le taux de sélection, ou le taux de faux positifs / faux négatifs varie-t-il fortement d'un groupe à l'autre ?
=> Un groupe est-il systématiquement moins sollicité ou moins bien servi par le modèle ?


### Scénario 4 (optionnel) : modèle minimal

Modèle minimal 
sans variables sensibles et sans historique de campagne 
pour tester la faisabilité d'un modèle reposant uniquement sur un socle de variables réduit

## Améliorer les Modèles et Choisir le Meilleur

c'est pas dans le sujet 
mais l'idée c'est quand même d'avoir le meilleur modèle possible
donc on améliorera le modèle 


# INDUSTRIALISATION — EXPOSER LA SOLUTION IA

## Passage en Production

### Exposer le modèle via une API

Exposez le modèle sous forme de service 
afin qu'un utilisateur non technique (conseiller, responsable de campagne)
puisse l'interroger.

Développer une API de prédiction FastAPI exposant au minimum :
- une route de prédiction (POST)
 prenant en entrée les caractéristiques d'un client et renvoyant la probabilité de souscription
- une route de santé (health) permettant de vérifier que le service fonctionne

API solide : valider les données entrantes, gérer les erreurs et journaliser les requêtes.

- validation des données entrantes
- une gestion propre des erreurs 
- et la journalisation de chaque requête (entrées, sortie, horodatage) 


### Concevoir l'architecture cible

Proposez une architecture cible
pour déployer la solution en conditions réelles, 
sous la forme d'un schéma simple des composants (Mermaid)

Contraintes de performance et d'infrastructure 
Le modèle mobilise des variables tabulaires (catégorielles encodées et numériques)

Évaluer le rapport performance / coût computationnel d'inférence
et discuter du choix de l'infrastructure d'hébergement :
- déploiement sur site (on-premise) pour des raisons de confidentialité des données 
- ou déploiement sur un Cloud souverain

Estimer la latence acceptable
pour un conseiller qui interroge le service avant de contacter un client
et dimensionner les ressources (CPU / RAM).

Identifiez les acteurs à mobiliser/consulter pour valider cette architecture 
(SI, conformité / DPO, équipe métier).


## Suivi : Mesurer la Performance et les Impacts en Production


les métriques d'entraînement ne suffisent plus une fois le modèle déployé
Proposez un suivi de la solution en production.

- Métriques techniques : temps de réponse, taux d'erreur, disponibilité. 
- Métriques métier :
  - écart entre le taux de souscription réel et la probabilité prédite
  - évolution du profil des clients contactés (dérive des données) 

Proposez un moyen simple 
de rendre ces indicateurs visibles à un utilisateur non technique
(tableau de bord)



## Évolution du Modèle dans le Temps : Faire Évoluer la Solution en Continu

- Fiabilité dans le temps : surveiller les performances et réentraîner le modèle si elles se dégradent.

Mettre en place un dispositif d’évaluation continue de la solution,
intégrée à votre chaîne de développement
au-delà de sa mise en production initiale 
== CI/CD

RÉ-ENTRAÎNAMENT
Implémenter les critères déclenchant un réentraînement du modèle
(dégradation d’une métrique de performance par exemple)
Expliquez en quoi le suivi d’une ou de plusieurs métriques 
permet d’observer l’évolution des performances de la solution.

BOUCLE DE RÉTROACTION
Mettre en place un mécanisme permettant d’intégrer les retours terrain 
dans le cycle d’amélioration via une boucle de rétroaction (feedback loop, exemple : les remontées des conseillers)

AUTOMATISATION CI/CD
Automatisez l’évaluation du modèle
ainsi que son réentraînement et son déploiement au sein d’une chaîne CI/CD 
(par exemple avec Github Actions) 
en fiabilisant les tests.

MAITRISE DES RISQUES 
Défirnir une stratégie limitant les risques d'une mise à jour en production
(par exemple : comparaison champion/challenger)
et imaginez une périodicité à laquelle la pertinence des indicateurs suivis sera réinterrogée.

BONUS : 
- conteneurisation avec Docker
- suivi des expériences avec MLflow (versions du modèle, hyperparamètres, métriques)
- interface graphique simple (Streamlit ou Gradio) permettant de saisir un profil via un formulaire
