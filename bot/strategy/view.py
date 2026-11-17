"""Ce que le bot sait au moment de décider, calculé une fois par appel de /play.

L'arbitre n'envoie que notre main, la réserve et les scores. Le reste (nos cartes,
nos actions, achats et argent restants) vient de notre mémoire (bot/memory.py).
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from bot.memory import GameMemory


def _quantities(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    quantities = raw.get("quantities")
    if not isinstance(quantities, dict):
        return {}
    return {str(card): qty for card, qty in quantities.items() if isinstance(qty, int)}


def _players(state: Any) -> list[dict]:
    if not isinstance(state, dict):
        return []
    return [p for p in state.get("players") or [] if isinstance(p, dict)]


def read_state(state: Any, team_name: str) -> tuple[dict[str, int], dict[str, int]]:
    """Notre main et la réserve.

    Seul le joueur dont c'est le tour a une main visible : c'est nous quand
    l'arbitre appelle /play.
    """
    if not isinstance(state, dict):
        return {}, {}
    with_hand = [p for p in _players(state) if isinstance(p.get("hand"), dict)]
    me = next((p for p in with_hand if p.get("name") == team_name), None)
    if me is None and with_hand:
        me = with_hand[0]
    hand = _quantities(me.get("hand")) if me else {}
    return {card: qty for card, qty in hand.items() if qty > 0}, _quantities(state.get("stock"))


def score_margins(state: Any, team_name: str) -> tuple[int, ...]:
    """Notre avance sur CHAQUE adversaire (négative si on est derrière), si on connaît les scores."""
    players = _players(state)
    mine = [p.get("score") for p in players if p.get("name") == team_name]
    others = [p.get("score") for p in players if p.get("name") != team_name]
    if len(mine) != 1 or not others or not all(isinstance(s, int) for s in [*mine, *others]):
        return ()
    return tuple(mine[0] - other for other in others)


def our_score(state: Any, team_name: str) -> int | None:
    """Notre score dans l'état envoyé par l'arbitre, s'il est lisible."""
    mine = [p.get("score") for p in _players(state) if p.get("name") == team_name]
    return mine[0] if len(mine) == 1 and isinstance(mine[0], int) else None


def our_seat(state: Any, team_name: str) -> int | None:
    """Notre place dans l'ordre de jeu : l'arbitre envoie les joueurs dans cet ordre."""
    names = [p.get("name") for p in _players(state)]
    return names.index(team_name) if names.count(team_name) == 1 else None


def score_lead(state: Any, team_name: str) -> int | None:
    """Notre avance (négative si on est derrière) sur le meilleur adversaire, si on la connaît."""
    margins = score_margins(state, team_name)
    return min(margins) if margins else None


@dataclass(frozen=True)
class View:
    hand: dict[str, int] = field(default_factory=dict)
    stock: dict[str, int] = field(default_factory=dict)
    empty_piles: int = 0  # piles de la réserve vidées depuis le début (3 vides : fin de partie)
    deck: Counter = field(default_factory=Counter)  # toutes nos cartes : départ + achats
    players: int = 2  # royaumes à la table, éliminés compris
    lead: int | None = None  # notre avance sur le meilleur adversaire (négative si derrière)
    margins: tuple[int, ...] = ()  # notre avance sur chaque adversaire, s'il y en a plusieurs
    money: int = 0  # argent disponible pour le prochain achat
    actions_left: int = 1
    buys_left: int = 1
    turn: int = 1  # numéro de notre tour dans la partie
    played: tuple[str, ...] = ()  # cartes Action déjà jouées ce tour
    bought_this_turn: bool = False
    # Achats de tous les adversaires réunis depuis le début (None : inconnus, mémoire perdue).
    # En duel, c'est exactement le deck de l'adversaire, jeu de départ en plus.
    others_bought: Counter | None = None
    seat: int | None = None  # notre place dans l'ordre de jeu (0 : on joue en premier), si on la connaît

    @property
    def provinces(self) -> int:
        """Provinces restantes dans la réserve."""
        return self.stock.get("province", 0)

    def available(self, card: str) -> bool:
        return self.stock.get(card, 0) > 0


def make_view(state: Any, memory: GameMemory, team_name: str) -> View:
    hand, stock = read_state(state, team_name)
    margins = score_margins(state, team_name)
    players = max(2, len(_players(state)))
    memory.observe_stock(stock, players)
    memory.count_curses(our_score(state, team_name))
    return View(
        hand=hand,
        stock=stock,
        empty_piles=memory.empty_piles(stock),
        deck=memory.deck(),
        players=players,
        lead=min(margins) if margins else None,
        margins=margins,
        money=memory.money_available(hand),
        actions_left=memory.actions_left,
        buys_left=memory.buys_left,
        turn=memory.turn,
        played=tuple(memory.played),
        bought_this_turn=memory.budget is not None,
        others_bought=Counter(memory.others_bought) if memory.others_known else None,
        seat=our_seat(state, team_name),
    )
