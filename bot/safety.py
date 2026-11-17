"""Choix pour les routes de décision (défausser, écarter, recevoir une carte...).

Règle d'or : une réponse invalide = disqualification.
Chaque fonction renvoie UNIQUEMENT une carte prise dans la liste reçue (ou un
booléen). bot/main.py revérifie quand même avant d'envoyer.

Quand l'arbitre appelle-t-il ces routes ? D'après le moteur public :
- discard_card_from_hand : Milice jouée par un ADVERSAIRE (on garde 3 cartes),
  nos Marquis et Braconnier
- trash_card_from_hand : nos Rénovation et Renouvellement
- choose_card_to_receive_in_discard : nos Atelier, Festin, Rénovation,
  Renouvellement, Troc
- choose_card_to_receive_in_deck : notre Maître artisan
- confirm_discard_card_from_hand : nos Cave et Maître artisan (carte par carte)
- confirm_trash_card_from_hand : nos Chapelle, Prêteur sur gages, Troc
- skip_card_reception_in_hand : notre Bibliothèque
- confirm_discard_deck : notre Chancelier
- trash_money_card_for_better_money_card : notre Mine
"""

from typing import TYPE_CHECKING

from bot.cards import info

if TYPE_CHECKING:
    from bot.memory import GameMemory
    from bot.strategy import Decision


def legal_play(decision: "Decision", hand: dict[str, int], stock: dict[str, int], memory: "GameMemory") -> bool:
    """La décision de /play respecte-t-elle les règles du moteur, d'après ce qu'on sait ?

    Dernier contrôle avant d'envoyer : une commande refusée par l'arbitre élimine le royaume.
    Mêmes règles que le test tests/proprietes/test_valid_commands.py.
    """
    if decision.kind == "END_TURN":
        return True
    card = decision.card
    if not card:
        return False
    if decision.kind == "ACTION":
        return hand.get(card, 0) > 0 and info(card).is_action and memory.actions_left >= 1 and memory.budget is None
    if decision.kind == "BUY":
        return memory.buys_left >= 1 and stock.get(card, 0) > 0 and info(card).cost <= memory.money_available(hand)
    return False


def keep_in_hand_value(card: str) -> float:
    """Intérêt de garder la carte en main ce tour-ci (plus bas = on s'en débarrasse)."""
    if card == "curse":
        return -2
    if card == "cursedgold":  # on évite de s'en servir (Malédiction)
        return -1
    c = info(card)
    if c.is_dead_in_hand:
        return 0
    if c.is_treasure:
        return c.money
    return 1 + c.cost / 10  # carte Action : utile seulement si on peut la jouer


def keep_in_deck_value(card: str) -> float:
    """Intérêt de garder la carte dans notre deck (plus bas = on l'écarte)."""
    if card == "curse":
        return -2  # l'écarter, c'est regagner 1 PV
    if card == "cursedgold":
        return -1
    c = info(card)
    return c.cost + 3 * c.victory_points


def gain_value(card: str) -> float:
    """Intérêt de recevoir la carte gratuitement (jamais de Malédiction si on a le choix)."""
    if card == "curse":
        return -100
    return info(card).cost


def choose_discard(hand: list[str]) -> str:
    return min(hand, key=keep_in_hand_value)


def choose_trash(hand: list[str]) -> str:
    return min(hand, key=keep_in_deck_value)


def choose_gain(possible_cards: list[str], memory: "GameMemory | None" = None) -> str:
    """Carte reçue gratuitement (Atelier : jusqu'à 4 pièces ; Festin : jusqu'à 5).

    Si on connaît la partie (`memory`), on prend ce que notre stratégie achèterait avec ce montant,
    parmi les cartes proposées : une Milice ou un Argent au début, un Duché à la fin... Sinon, la plus
    chère, et à coût égal la première par ordre alphabétique (l'ordre de la liste change d'une fois
    à l'autre, notre choix non)."""
    choice = _strategy_gain(possible_cards, memory) if memory is not None else None
    return choice or max(sorted(possible_cards), key=gain_value)


def _strategy_gain(possible_cards: list[str], memory: "GameMemory") -> str | None:
    try:
        from bot.strategy import GROUPE3, View, buy_choice

        known = memory.seen_stock or {}
        top = max(info(card).cost for card in possible_cards)
        # La réserve telle qu'on la connaît, sans les cartes qu'on ne nous propose pas (les plus
        # chères restent : la fin de partie se décide d'après les Provinces restantes).
        stock = {card: qty for card, qty in known.items() if card in possible_cards or info(card).cost > top}
        for card in possible_cards:
            stock.setdefault(card, 1)
        players = min(max(memory.players, 2), 4)
        view = View(stock=stock, deck=memory.deck(), players=players, money=top, buys_left=1)
        choice = buy_choice(view, top, GROUPE3[players])
    except Exception:  # noqa: BLE001 - au pire, le choix simple
        return None
    return choice if choice in possible_cards and choice != "curse" else None


def confirm_discard(card: str, hand: list[str]) -> bool:  # noqa: ARG001
    """Cave, Maître artisan : on défausse seulement ce qui est mort en main."""
    return keep_in_hand_value(card) <= 0


def confirm_trash(card: str, hand: list[str]) -> bool:  # noqa: ARG001
    """Chapelle, Prêteur sur gages, Troc : on n'écarte que Malédictions, Or maudit et Cuivres."""
    return card in ("curse", "cursedgold", "copper")


def skip_card_reception(card: str, hand: list[str]) -> bool:  # noqa: ARG001
    """Bibliothèque : on saute les cartes Action (plus d'action pour les jouer)."""
    return True


def confirm_discard_deck() -> bool:
    """Chancelier : on garde notre deck tel quel."""
    return False


def choose_mine(money_in_hand: list[str]) -> str:
    """Mine : on améliore un trésor (Or maudit → Or, Argent → Or, Cuivre → Argent)."""
    for card in ("cursedgold", "silver", "copper"):
        if card in money_in_hand:
            return card
    return money_in_hand[0]
