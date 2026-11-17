#!/bin/sh
# Lance un bot sur Alwaysdata (site de type « Programme utilisateur ») avec la dernière version de sa
# branche sur GitHub. Commande du site, à mettre une fois dans Alwaysdata (Web > Sites > Modifier) :
#
#   officiel : sh -c 'cd $HOME && (test -d bot || git clone -q https://github.com/Papaille007/Bowser.git bot) && exec sh bot/lancer.sh main "BOWSER"'
#   test     : sh -c 'cd $HOME && (test -d bot || git clone -q https://github.com/Papaille007/Bowser.git bot) && exec sh bot/lancer.sh younes "KOOPA DOMINION test"'
#
# Mettre en ligne une nouvelle version = pousser sur la branche, puis « Redémarrer » le site.
# Le tout est entre accolades : ce script est lu en entier avant de se mettre à jour lui-même.
{
    BRANCHE="${1:-main}"
    NOM="${2:-BOWSER}"
    cd "$(dirname "$0")" || exit 1
    git fetch -q origin "$BRANCHE" && git checkout -q -f -B "$BRANCHE" "origin/$BRANCHE"
    if [ ! -x .venv/bin/uvicorn ] || ! cmp -s requirements.txt .venv/requirements.txt; then
        PY=$(command -v python3.12 || command -v python3 || command -v python)
        rm -rf .venv && "$PY" -m venv .venv && .venv/bin/pip install -q -r requirements.txt && cp requirements.txt .venv/requirements.txt
    fi
    export DOPYNION_TEAM_NAME="$NOM"
    exec .venv/bin/uvicorn bot.main:app --host "$IP" --port "$PORT"
}
