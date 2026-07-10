# PAIE-ENVOI

Outil interne : rapprocher les **bulletins de paie** et les **relevés mensuels
(Thésée)** par nom/prénom, les **fusionner en un PDF par client**, et les
**envoyer par email** en un clic. Tout est local (Streamlit + SQLite) ; les
documents ne transitent que par votre propre serveur d'email.

## Installation (une fois)

```bash
cd ~/PAIE-ENVOI
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

L'email expéditeur se configure directement dans l'app, onglet **⚙️ Mon email**
(adresse + mot de passe ; serveur SMTP détecté automatiquement pour les
fournisseurs courants, bouton « Tester la connexion »). Les identifiants sont
enregistrés en local dans `.env` — éditable à la main si besoin (`.env.example`).

## Utilisation (chaque mois)

```bash
.venv/bin/streamlit run app.py
```

0. **Type d'envoi** en tête de l'onglet : mensuel (bulletin + relevé fusionnés)
   ou hebdomadaire (relevé seul).
1. **Période** dans la barre latérale (ex. « Juin 2026 », « Semaine 28 »).
2. **Excel clients** : colonnes Nom, Prénom, Email (casse/accents indifférents).
3. **PDF** : glisser les bulletins d'un côté, les relevés Thésée de l'autre.
4. **Rapprochement** automatique par nom+prénom (dans le texte du PDF, sinon
   dans le nom du fichier) — corrigeable à la main, dossiers incomplets signalés.
5. **Fusion** : un PDF `NOM_Prenom_Periode.pdf` par client dans `data/fusions/`.
6. **Envoi** : email de test recommandé, puis envoi groupé après confirmation.
   Un client déjà servi pour la période n'est **jamais renvoyé** (journal SQLite
   dans `data/journal.db`, consultable dans l'app).

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/
```

## Sécurité et accès

- **Mot de passe obligatoire** à l'ouverture de l'app (hachage SHA-256 dans
  `.env`, clé `APP_MDP_SHA256` — jamais stocké en clair). Pour le changer :
  `.venv/bin/python -c "from pathlib import Path; from paie.acces import hacher; from paie.config import enregistrer_env; enregistrer_env(Path('.env'), {'APP_MDP_SHA256': hacher('NOUVEAU_MDP')})"`
- **Accès réseau local ouvert** (`.streamlit/config.toml`, `address = "0.0.0.0"`) :
  les collègues du bureau utilisent l'app via `http://<IP-du-Mac>:8501` pendant
  qu'elle tourne (IP : `ipconfig getifaddr en0`). Pour revenir à un accès
  strictement local, remettre `address = "127.0.0.1"`.
- Le trafic sur le réseau local est en HTTP simple : le mot de passe et les
  documents circulent en clair sur le LAN du bureau — ne pas utiliser depuis
  un Wi-Fi public ou partagé avec des inconnus.

## Notes

- Les bulletins de paie sont des données personnelles sensibles : `data/` et
  `.env` ne doivent jamais quitter ce poste (ils sont dans `.gitignore`).
- PDF scannés sans texte (image seule) : le rapprochement se rabat sur le nom
  du fichier ; sinon, associer manuellement à l'étape 3.
- Gmail/iCloud exigent un « mot de passe d'application » (pas le mot de passe
  du compte) pour le SMTP.
- Évolution possible : téléchargement automatique des relevés depuis Thésée
  (navigateur piloté), sur demande.
