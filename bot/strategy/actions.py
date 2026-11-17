"""Phase Action : quelle carte Action jouer (responsable : Alexandre).

Garde-fous (sinon élimination par l'arbitre) : une carte de notre main, une action
restante, rien acheté ce tour, et seulement des cartes sans aucun choix à faire : effets
fixes (+cartes, +actions, +achats, +pièces) ou effets sans choix (Sorcière, Recrue...,
voir bot/cards.py). Une carte inconnue ou qui demande un choix (Milice, Chapelle...)
n'est jamais jouée.

Ordre : d'abord les cartes qui rendent une action (Laboratoire, Marché, Village,
Festival...). Puis, parmi celles qui n'en rendent pas : la Sorcière tant qu'il reste
des Malédictions à donner, la Recrue (une carte de plus à chaque tour, pour le reste
de la partie), puis celles qui piochent le plus (Chambre du conseil, Forgeron), puis
celles qui rapportent. Avec `hireling_first` (le réglage de GROUPE3), la Recrue passe
avant la Sorcière : son +1 carte vaut pour tous les tours suivants (+1,2 point en duel).
"""

from bot.cards import info
from bot.strategy.view import View


def cards_drawn(card: str, hand: dict[str, int] | None = None) -> int:
    """Cartes que la carte nous fait piocher. Pour les cartes du 16/11, ça dépend de la main : le Magnat
    pioche une carte par Trésor en main, la Bibliothèque complète la main à 7 cartes (elle-même une fois
    jouée n'y est plus), l'Aventurier ramène 2 Trésors."""
    hand = hand or {}
    if card == "magnate":
        return sum(quantity for other, quantity in hand.items() if info(other).is_treasure)
    if card == "library":
        return max(0, 7 - (sum(hand.values()) - 1)) if hand else 2
    if card == "adventurer":
        return 2
    return info(card).plus_cards


def action_priority(
    card: str, curses_left: bool = True, hireling_first: bool = False, hand: dict[str, int] | None = None
) -> tuple:
    c = info(card)
    first = 0  # Sorcière et Recrue avant les autres cartes qui ne rendent pas d'action
    if card == "witch" and curses_left:
        first = 2
    elif card == "hireling":
        first = 3 if hireling_first else 1
    return (c.plus_actions >= 1, first, cards_drawn(card, hand), c.plus_money, c.plus_buys)


def choose_action(view: View, hireling_first: bool = False) -> str | None:
    """Carte Action à jouer, ou None pour passer aux achats."""
    if view.actions_left <= 0 or view.bought_this_turn:
        return None
    playable = [card for card in view.hand if info(card).is_simple_action]
    if not playable:
        return None
    curses_left = view.available("curse")
    return max(sorted(playable), key=lambda card: action_priority(card, curses_left, hireling_first, view.hand))
