"""Copie de la stratégie de Koopa Dominion, le bot actuel de l'équipe (repo Bowser, 08/10).

Sert uniquement de référence dans le simulateur et au championnat local : une seule
action par tour, un seul achat, argent compté sur les trésors en main.
"""

from bot.strategy.base import END_TURN, Decision, register
from bot.strategy.view import View

KOOPA_ACTIONS = ["smithy", "village", "market", "woodcutter", "festival", "laboratory"]
KOOPA_BUYS = [
    (8, "province"), (6, "gold"), (5, "duchy"), (5, "festival"), (5, "laboratory"),
    (5, "market"), (4, "smithy"), (3, "silver"), (3, "village"), (3, "woodcutter"),
    (2, "estate"), (0, "copper"),
]  # fmt: skip


def koopa(view: View) -> Decision:
    if not view.played and not view.bought_this_turn:
        card = next((c for c in KOOPA_ACTIONS if view.hand.get(c, 0) > 0), None)
        if card is not None:
            return Decision("ACTION", card)
    if view.bought_this_turn:
        return Decision(END_TURN)
    money = view.hand.get("copper", 0) + 2 * view.hand.get("silver", 0) + 3 * view.hand.get("gold", 0)
    card = next((c for cost, c in KOOPA_BUYS if money >= cost and view.available(c)), None)
    return Decision("BUY", card) if card else Decision(END_TURN)


register("koopa", koopa)
