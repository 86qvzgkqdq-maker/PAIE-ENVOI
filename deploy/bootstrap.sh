#!/bin/bash
# Déploiement complet de PAIE-ENVOI sur un VPS Ubuntu fraîchement installé.
#
# Usage, en une commande sur le serveur :
#   curl -sL https://raw.githubusercontent.com/86qvzgkqdq-maker/PAIE-ENVOI/main/deploy/bootstrap.sh | sudo bash -s paie.lamaisonduchauffeurvtc.fr
#
# Prérequis : le sous-domaine (paie.<domaine>) doit pointer vers l'IP du VPS (DNS A).
# Les identifiants email s'ajoutent ensuite dans /opt/paie-envoi/.env (voir fin).
set -euo pipefail

DOMAINE="${1:?Usage: ... | sudo bash -s paie.votredomaine.fr}"
REPO="https://github.com/86qvzgkqdq-maker/PAIE-ENVOI.git"
APP=/opt/paie-envoi

echo "==> Déploiement de PAIE-ENVOI sur $DOMAINE"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip git curl gnupg \
    debian-keyring debian-archive-keyring apt-transport-https

# --- Caddy (HTTPS automatique) ---
if ! command -v caddy >/dev/null 2>&1; then
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
    apt-get update -qq && apt-get install -y -qq caddy
fi

# --- Code + environnement Python ---
if [ -d "$APP/.git" ]; then
    git -C "$APP" pull --ff-only
else
    rm -rf "$APP"; git clone --depth 1 "$REPO" "$APP"
fi
python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install --quiet --upgrade pip
"$APP/.venv/bin/pip" install --quiet -r "$APP/requirements.txt"

# --- .env : au minimum le mot de passe d'accès, pour que l'app soit protégée
#     dès la première seconde (identifiants email ajoutés ensuite). ---
if [ ! -f "$APP/.env" ]; then
    echo "APP_MDP_SHA256=b405756cf4f642f8bab13ec5066762497fb19b72f058f0c0b095006fce28bb9a" > "$APP/.env"
    chmod 600 "$APP/.env"
fi

# --- Service systemd (redémarrage automatique) ---
cat > /etc/systemd/system/paie-envoi.service <<'SERVICE'
[Unit]
Description=PAIE-ENVOI (Streamlit)
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/paie-envoi
ExecStart=/opt/paie-envoi/.venv/bin/streamlit run app.py \
    --server.address 127.0.0.1 --server.port 8501 \
    --server.headless true --browser.gatherUsageStats false
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

# --- Caddy : reverse-proxy HTTPS vers l'app ---
cat > /etc/caddy/Caddyfile <<CADDY
$DOMAINE {
	reverse_proxy 127.0.0.1:8501
}
CADDY

systemctl daemon-reload
systemctl enable --now paie-envoi
systemctl enable caddy
systemctl restart caddy

echo ""
echo "==> Terminé. L'app tourne (protégée par mot de passe)."
echo "    Vérifier : systemctl status paie-envoi caddy --no-pager"
echo "    URL      : https://$DOMAINE"
echo ""
echo "==> Dernière étape : ajouter les identifiants email dans /opt/paie-envoi/.env"
echo "    puis : systemctl restart paie-envoi"
