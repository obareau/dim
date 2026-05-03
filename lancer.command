#!/bin/bash
# D.I.M — Dawless Is More
# Launcher macOS — double-clic depuis le Finder

# Aller dans le dossier du script (même si lancé depuis ailleurs)
cd "$(dirname "$0")"

echo ""
echo "  D · I · M — Dawless Is More"
echo "  ─────────────────────────────"

# Créer le venv si absent
if [ ! -d ".venv" ]; then
  echo "  → Création de l'environnement virtuel..."
  python3 -m venv .venv
  source .venv/bin/activate
  echo "  → Installation des dépendances..."
  pip install -r requirements.txt --quiet
else
  source .venv/bin/activate
fi

echo "  → Démarrage du serveur..."
echo ""

# Ouvrir le navigateur après 1.5s (le serveur a le temps de démarrer)
(sleep 1.5 && open "http://localhost:5002/performance") &

# Lancer le serveur (bloque jusqu'à Ctrl+C)
python adapters/web/app.py

echo ""
echo "  Serveur arrêté."
