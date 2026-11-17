"""Le cerveau du bot : les décisions de la route /play.

Format confirmé par le client (réunion du 08/10) :
- "BUY <carte>"    : acheter une carte de la réserve ;
- "ACTION <carte>" : jouer une carte Action de notre main ;
- "END_TURN"       : finir le tour (ou ne jouer aucune action).
Après chaque décision, l'arbitre rappelle /play avec le nouvel état.

Un fichier par brique, un responsable par fichier (voir docs/organisation.md) :
- view.py            ce que le bot sait (état reçu + notre mémoire)
- actions.py         phase Action                       (Alexandre)
- economy.py         achats d'économie                  (Pauline)
- endgame.py         cartes Victoire, fin de partie     (Jean-Eudes)
- plans.py           assemblage des briques, registre   (Younes)
- koopa.py           copie du bot actuel de l'équipe, pour comparer
- essais_<prénom>.py bac à sable de chacun, chargé automatiquement
"""

import importlib
import pkgutil
import sys
from typing import Any

from bot.memory import GameMemory
from bot.strategy import koopa as _koopa  # noqa: F401 - enregistre "koopa"
from bot.strategy.actions import choose_action
from bot.strategy.base import END_TURN, STRATEGIES, Decision, Strategy, passive, register
from bot.strategy.duel import duel_buy
from bot.strategy.economy import Economy, economy_buy, smithy_allowed
from bot.strategy.endgame import Endgame, endgame_buy, pile_finish, province_ok
from bot.strategy.lookahead import lookahead_buy
from bot.strategy.plans import (
    BIG_MONEY,
    GROUPE3,
    GROUPE3_V1,
    GROUPE3_V2,
    GROUPE3_V3,
    GROUPE3_V4,
    GROUPE3_V5,
    GROUPE3_V6,
    GROUPE3_V7,
    GROUPE3_V8,
    GROUPE3_V9,
    GROUPE3_V10,
    SMITHY_BM,
    Plan,
    buy_choice,
    by_players,
    plan_strategy,
)
from bot.strategy.view import View, make_view, read_state, score_lead, score_margins

# Bacs à sable : chaque fichier essais_<prénom>.py est chargé et peut enregistrer ses stratégies.
# Un bac à sable cassé ne doit jamais empêcher le bot de démarrer.
for _module in pkgutil.iter_modules(__path__):
    if _module.name.startswith("essais_"):
        try:
            importlib.import_module(f"{__name__}.{_module.name}")
        except Exception as exc:  # noqa: BLE001
            print(f"[stratégie] bac à sable {_module.name} ignoré : {exc!r}", file=sys.stderr)


def decide_play(
    state: Any,
    memory: GameMemory,
    strategy: str,
    team_name: str,
    registry: dict[str, Strategy] | None = None,
) -> Decision:
    if isinstance(state, dict) and state.get("finished"):
        return Decision(END_TURN)
    if not memory.turn_started:
        # /start_turn jamais reçu pour cette partie (serveur redémarré en plein tour ?) :
        # on ne connaît ni nos actions ni nos achats restants, donc on ne prend aucun risque.
        return Decision(END_TURN)
    view = make_view(state, memory, team_name)
    return (registry or STRATEGIES).get(strategy, passive)(view)


__all__ = [
    "BIG_MONEY",
    "END_TURN",
    "GROUPE3",
    "GROUPE3_V1",
    "GROUPE3_V2",
    "GROUPE3_V3",
    "GROUPE3_V4",
    "GROUPE3_V5",
    "GROUPE3_V6",
    "GROUPE3_V7",
    "GROUPE3_V8",
    "GROUPE3_V9",
    "GROUPE3_V10",
    "SMITHY_BM",
    "STRATEGIES",
    "Decision",
    "Economy",
    "Endgame",
    "Plan",
    "Strategy",
    "View",
    "buy_choice",
    "by_players",
    "choose_action",
    "decide_play",
    "duel_buy",
    "economy_buy",
    "endgame_buy",
    "lookahead_buy",
    "make_view",
    "passive",
    "pile_finish",
    "plan_strategy",
    "province_ok",
    "read_state",
    "register",
    "score_lead",
    "score_margins",
    "smithy_allowed",
]
