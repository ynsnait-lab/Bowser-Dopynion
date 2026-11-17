"""Mémoire par partie.

L'arbitre ne nous envoie ni notre deck, ni notre défausse, ni nos actions,
achats ou argent restants (« il regarde automatiquement », réunion du 08/10) :
on les suit nous-mêmes, partie par partie (clé = x-game-id), en appliquant
exactement les mêmes règles que le moteur :
- début de tour : 1 action, 1 achat, 0 pièce bonus ;
- jouer une carte Action coûte 1 action et ajoute ses bonus ;
- l'argent disponible pour acheter = bonus des cartes jouées + trésors en main,
  moins ce qu'on a déjà dépensé dans le tour.
"""

from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bot.cards import STARTING_DECK, hand_money, info

if TYPE_CHECKING:
    from bot.strategy import Decision

MAX_GAMES_IN_MEMORY = 500

KINGDOM_PILE = 10  # cartes par pile de Royaume (les Jardins : autant que de Duchés)


def initial_stock(players: int, stock: dict[str, int]) -> dict[str, int]:
    """Réserve du début de partie, selon les règles du moteur dopynion 0.9.4 (02/11) : 8 cartes
    Victoire par pile à 2 joueurs (12 au-delà), 60 Cuivres moins 7 par joueur. Le moteur 0.9.3
    (son bug : 12 cartes Victoire et 60 Cuivres à toutes les tailles) se reconnaît à une pile plus
    grosse que prévu : on prend alors ses quantités, pour suivre l'arbitre quel qu'il soit."""
    victory = 8 if players <= 2 else 12
    copper = 60 - 7 * players
    if any(stock.get(card, 0) > victory for card in ("estate", "duchy", "province", "gardens")):
        victory = 12
    if stock.get("copper", 0) > copper:
        copper = 60
    base = {"copper": copper, "silver": 40, "gold": 30, "estate": victory, "duchy": victory, "province": victory}
    # Le moteur 0.9.4 inscrit aussi 8 Colonies dans la réserve en duel, sans que la carte soit en jeu.
    return {**base, "gardens": victory, "colony": victory}


# Carte reçue quand on joue ces cartes (dans la défausse ou sur la pioche : dans le deck, en tout cas).
GAINED_WHEN_PLAYED = {"distantshore": "estate", "bandit": "gold", "bureaucrat": "silver"}


@dataclass
class GameMemory:
    turn: int = 0
    # False tant qu'on n'a pas vu /start_turn (ex. serveur redémarré en plein tour) :
    # dans ce cas on ne connaît pas l'état du tour, donc on le termine sans rien faire.
    turn_started: bool = False
    actions_left: int = 1
    buys_left: int = 1
    action_money: int = 0  # pièces apportées par les cartes Action jouées ce tour
    budget: int | None = None  # argent total disponible, figé au premier achat du tour
    spent: int = 0
    played: list[str] = field(default_factory=list)  # cartes Action jouées ce tour
    bought: list[str] = field(default_factory=list)  # tous nos achats de la partie
    # Depuis le 26/10 (nouvelles cartes du site) : cartes reçues sans les acheter (Malédictions des
    # Sorcières adverses, Domaines de nos Rivages lointains) et cartes sorties du deck (nos Recrues
    # jouées, mises de côté pour toute la partie).
    gained: Counter[str] = field(default_factory=Counter)
    removed: Counter[str] = field(default_factory=Counter)
    piles: set[str] = field(default_factory=set)  # piles de la réserve vues depuis le début de la partie
    # Achats des adversaires (tous ensemble), lus dans la réserve entre deux de nos décisions :
    # ce qui a disparu de la réserve sans que ce soit nous l'a acheté un adversaire. Ce Royaume
    # n'a ni rebut ni gain : leurs achats + leur jeu de départ = toutes leurs cartes.
    seen_stock: dict[str, int] | None = None  # réserve à notre dernière décision, nos achats retirés
    others_bought: Counter[str] = field(default_factory=Counter)
    others_known: bool = True  # False si on a raté des achats (mémoire perdue en pleine partie)
    players: int = 2  # joueurs à la table, vu dans l'état reçu

    def new_turn(self) -> None:
        self.turn += 1
        self.turn_started = True
        self.actions_left = 1
        self.buys_left = 1
        self.action_money = 0
        self.budget = None
        self.spent = 0
        self.played = []

    def money_available(self, hand: dict[str, int]) -> int:
        if self.budget is not None:
            return self.budget - self.spent
        return self.action_money + hand_money(hand)

    def deck(self) -> Counter[str]:
        """Toutes nos cartes : jeu de départ + achats + cartes reçues - Recrues mises de côté."""
        return Counter(STARTING_DECK) + Counter(self.bought) + self.gained - self.removed

    def count_curses(self, score: int | None) -> None:
        """Nos Malédictions : l'arbitre ne dit pas qui en reçoit, mais notre score les compte
        (-1 point chacune). Points de nos cartes connues moins notre score = nos Malédictions."""
        if score is None or score < -1000:  # score illisible, ou royaume éliminé (-10000)
            return
        known = self.deck() - Counter({"curse": self.gained["curse"]})
        points = sum(info(card).victory_points * qty for card, qty in known.items())
        self.gained["curse"] = max(0, points - score)

    def empty_piles(self, stock: dict[str, int]) -> int:
        """Piles de la réserve vidées depuis le début de la partie (3 vides : fin de partie).

        L'arbitre n'envoie pas les piles vides : on retient toutes celles qu'on a déjà vues.
        Mémoire perdue en pleine partie (serveur redémarré) : on en compte moins, jamais trop.
        """
        if not stock:
            return 0  # réserve illisible : on ne sait rien
        self.piles.update(card for card, quantity in stock.items() if quantity > 0)
        return sum(1 for card in self.piles if stock.get(card, 0) <= 0)

    def observe_stock(self, stock: dict[str, int], players: int) -> None:
        """Ajoute aux achats des adversaires ce qui a quitté la réserve depuis notre dernière décision.

        Première fois qu'on voit la réserve : on la compare à celle du début de partie. Si l'écart
        dépasse un achat par adversaire (seuls des adversaires ont pu jouer avant notre 1ᵉʳ tour),
        c'est que notre mémoire a été perdue en pleine partie : on ne sait plus rien de leurs cartes.
        """
        if not stock:
            return  # réserve illisible : on garde ce qu'on sait
        self.players = players
        before = self.seen_stock
        if before is None:
            start = initial_stock(players, stock)
            before = {card: start.get(card, KINGDOM_PILE) for card in stock}
            if sum(max(0, q - stock.get(c, 0)) for c, q in before.items()) > players - 1:
                self.others_known = False
        for card, quantity in before.items():
            if card == "curse":
                continue  # une Malédiction n'est pas un achat : la Sorcière la donne (à nous aussi)
            if quantity > stock.get(card, 0):
                self.others_bought[card] += quantity - stock.get(card, 0)
        self.seen_stock = dict(stock)

    def record(self, decision: Decision, hand: dict[str, int]) -> None:
        if decision.kind == "ACTION" and decision.card:
            card = info(decision.card)
            self.actions_left += card.plus_actions - 1
            self.buys_left += card.plus_buys
            self.action_money += card.plus_money
            self.played.append(decision.card)
            if decision.card in ("hireling", "feast"):  # Recrue mise de côté, Festin écarté : hors du deck
                self.removed[decision.card] += 1
            elif decision.card in GAINED_WHEN_PLAYED:  # Rivage lointain, Bandit, Bureaucrate
                gain = GAINED_WHEN_PLAYED[decision.card]
                self.gained[gain] += 1
                if self.seen_stock is not None:  # ... une carte qui quitte la réserve sans qu'un adversaire l'achète
                    self.seen_stock[gain] = self.seen_stock.get(gain, 0) - 1
        elif decision.kind == "BUY" and decision.card:
            if self.budget is None:
                self.budget = self.money_available(hand)
            self.spent += info(decision.card).cost
            self.buys_left -= 1
            self.actions_left = 0  # après un achat, on ne joue plus d'action
            self.bought.append(decision.card)
            if self.seen_stock is not None:  # notre achat n'est pas celui d'un adversaire
                self.seen_stock[decision.card] = self.seen_stock.get(decision.card, 0) - 1

    def record_gain(self, card: str) -> None:
        """Carte reçue sans l'acheter, choisie par nous (Atelier, Festin) : dans notre deck, et ce
        n'est pas un adversaire qui l'a prise dans la réserve."""
        self.gained[card] += 1
        if self.seen_stock is not None:
            self.seen_stock[card] = self.seen_stock.get(card, 0) - 1


class MemoryStore:
    """Plusieurs parties peuvent tourner en même temps : accès protégé par un verrou."""

    def __init__(self) -> None:
        self._games: dict[str, GameMemory] = {}
        self._lock = threading.Lock()

    def get(self, game_id: str) -> GameMemory:
        with self._lock:
            if game_id not in self._games and len(self._games) >= MAX_GAMES_IN_MEMORY:
                # Parties jamais terminées (end_game manqué) : on oublie la plus ancienne.
                self._games.pop(next(iter(self._games)))
            return self._games.setdefault(game_id, GameMemory())

    def forget(self, game_id: str) -> None:
        with self._lock:
            self._games.pop(game_id, None)

    def clear(self) -> None:
        with self._lock:
            self._games.clear()

    def __len__(self) -> int:
        return len(self._games)


memories = MemoryStore()
