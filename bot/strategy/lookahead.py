"""Fin de partie à 3 et 4 joueurs : on la joue d'avance, quelques centaines de fois (responsable : Jean-Eudes).

À plusieurs, la réserve ne dit pas qui a acheté quoi, seulement ce que les adversaires ont acheté
tous ensemble (bot/memory.py) : on prête à chacun un deck moyen, jeu de départ + sa part des achats.
Pour chaque achat possible avec 8 pièces (des Provinces ou pas), on joue la suite de la partie
plusieurs centaines de fois, tour par tour dans l'ordre de jeu : chacun tire une main au hasard
dans son deck, nous avec nos réglages de fin de partie, les adversaires comme un bot « Big Money »
classique (la dernière Province seulement s'ils passent alors devant tout le monde). On garde
l'achat qui nous fait gagner le plus de duels en moyenne : l'ELO compte chaque adversaire.
Les mêmes tirages servent pour chaque achat comparé : l'écart ne vient que de l'achat.
"""

import random
from bisect import bisect
from collections import Counter
from dataclasses import dataclass

from bot.cards import STARTING_DECK
from bot.strategy.duel import DUCHY, ESTATE, PROVINCE, deck_key, turn_odds
from bot.strategy.endgame import Endgame, tie_result
from bot.strategy.view import View

GAMES = 300  # fins de partie jouées par achat comparé
MAX_TURNS = 40  # tours joués au plus après le nôtre : au-delà, on compte les points tels quels
OPPONENT = Endgame(finish_share=1.0)  # un adversaire « Big Money » : réglages de fin de partie par défaut
OUT = -1000  # score d'un joueur éliminé (l'arbitre lui met -10000) : il ne joue plus
# Une égalité compte pour un demi-duel, comme dans notre règle de fin de partie à 3 et 4 joueurs
# (finish_share). Mesuré le 26/10 : à 0, le calcul fait un peu moins bien que nos seuils.
TIE = 0.5


@dataclass
class Table:
    """Ce qui compte pour la fin de partie : piles de cartes Victoire et scores (index = ordre de jeu)."""

    provinces: int
    duchies: int
    estates: int
    empty_piles: int
    scores: list[int]

    def copy(self) -> "Table":
        return Table(self.provinces, self.duchies, self.estates, self.empty_piles, list(self.scores))

    @property
    def over(self) -> bool:
        return self.provinces <= 0 or self.empty_piles >= 3

    def take(self, who: int, card: str) -> bool:
        """Achète une carte Victoire pour `who` (False si sa pile est vide)."""
        if card == "province" and self.provinces > 0:
            self.provinces -= 1
            self.scores[who] += PROVINCE
        elif card == "duchy" and self.duchies > 0:
            self.duchies -= 1
            self.scores[who] += DUCHY
            self.empty_piles += self.duchies == 0
        elif card == "estate" and self.estates > 0:
            self.estates -= 1
            self.scores[who] += ESTATE
            self.empty_piles += self.estates == 0
        else:
            return False
        return True

    def duels(self, who: int, extra: int = 0, tie: float = 0.5, rule: str = "inconnue") -> float:
        """Duels que `who` gagne si la partie s'arrête avec `extra` points de plus pour lui
        (index = place à la table : une égalité se compte selon la règle du site, sinon `tie`)."""
        mine = self.scores[who] + extra
        return sum(
            1.0 if mine > s else tie_result(rule, who, i, tie) if mine == s else 0.0
            for i, s in enumerate(self.scores)
            if i != who
        )


def play_buys(table: Table, who: int, money: int, buys: int, end: Endgame) -> None:
    """Cartes Victoire achetées par `who` avec ces règles de fin de partie (les mêmes qu'endgame.py,
    sans les Ors : tout à la fin, on n'en achète plus pour gagner)."""
    others = len(table.scores) - 1
    for _ in range(buys):
        p = table.provinces
        if money >= 8 and p > 0 and (p > 1 or table.duels(who, PROVINCE, rule=end.ties) >= end.finish_share * others):
            table.take(who, "province")
            money -= 8
        elif (money >= 6 and p <= end.duchy_with_6_at) or (money == 5 and p <= end.duchy_with_5_at):
            if table.take(who, "duchy"):
                money -= 5
            elif end.estate_without_duchy and table.take(who, "estate"):
                money -= 2
            else:
                break
        elif (3 <= money <= 4 and p <= end.estate_with_3_at) or (money == 2 and p <= end.estate_with_2_at):
            if not table.take(who, "estate"):
                break
            money -= 2
        else:
            break


Hands = tuple[list[tuple[int, int]], list[float]]  # mains possibles (argent, achats) et probabilités cumulées


def _hands(odds: tuple[tuple[int, int, float], ...]) -> Hands:
    outcomes, cumulative, total = [], [], 0.0
    for money, buys, prob in odds:
        total += prob
        outcomes.append((money, buys))
        cumulative.append(total)
    return outcomes, cumulative


def play_out(table: Table, order: list[int], hands: dict, plans: dict, draws: list[float]) -> Table:
    """Joue la suite de la partie : un tour par joueur, dans l'ordre de jeu, une main tirée par tour."""
    for who, draw in zip(order, draws, strict=False):
        outcomes, cumulative = hands[who]
        money, buys = outcomes[min(bisect(cumulative, draw), len(outcomes) - 1)]
        play_buys(table, who, money, buys, plans[who])
        if table.over:
            break
    return table


def _choices(money: int, buys: int, table: Table) -> list[tuple[str, ...]]:
    """Nos achats possibles : pour chaque nombre de Provinces, le plus de points avec le reste."""
    choices = []
    for taken in range(min(buys, table.provinces, money // 8) + 1):
        cards, left, duchies, estates = ["province"] * taken, money - 8 * taken, table.duchies, table.estates
        for _ in range(buys - taken):
            if left >= 5 and duchies > 0:
                cards, left, duchies = [*cards, "duchy"], left - 5, duchies - 1
            elif left >= 2 and estates > 0:
                cards, left, estates = [*cards, "estate"], left - 2, estates - 1
        choices.append(tuple(cards))
    return choices


def lookahead_buy(view: View, money: int, end: Endgame) -> str | None:
    """Carte Victoire choisie en jouant la fin de partie d'avance ("" : aucune), ou None quand ça ne
    s'applique pas : moins de 3 joueurs, moins de 8 pièces, trop tôt (P > end.lookahead_at), ordre
    de jeu, scores ou cartes adverses inconnus."""
    players, provinces = view.players, view.provinces
    if players < 3 or money < 8 or not 0 < provinces <= end.lookahead_at:
        return None
    if view.others_bought is None or view.seat is None or len(view.margins) != players - 1:
        return None
    me = view.seat
    others = [-margin for margin in view.margins]
    scores = [*others[:me], 0, *others[me:]]
    table = Table(provinces, view.stock.get("duchy", 0), view.stock.get("estate", 0), view.empty_piles, scores)
    alive = [i for i, score in enumerate(scores) if score > OUT]
    order = [alive[(alive.index(me) + 1 + k) % len(alive)] for k in range(MAX_TURNS)]
    share = Counter({card: round(qty / (players - 1)) for card, qty in view.others_bought.items()})
    theirs = _hands(turn_odds(deck_key(Counter(STARTING_DECK) + share)))
    hands = dict.fromkeys(alive, theirs) | {me: _hands(turn_odds(deck_key(view.deck)))}
    plans = dict.fromkeys(alive, OPPONENT) | {me: end}
    rng = random.Random(repr((scores, provinces, deck_key(view.deck), deck_key(share))))
    draws = [[rng.random() for _ in range(MAX_TURNS)] for _ in range(end.lookahead_games)]
    best: tuple[tuple[float, int], tuple[str, ...]] | None = None
    for cards in _choices(money, min(view.buys_left, 2), table):
        start = table.copy()
        for card in cards:
            start.take(me, card)
        if start.over:
            value = start.duels(me, tie=TIE, rule=end.ties)
        else:
            games = (play_out(start.copy(), order, hands, plans, d).duels(me, tie=TIE, rule=end.ties) for d in draws)
            value = sum(games) / len(draws)
        key = (round(value, 9), start.scores[me])
        if best is None or key > best[0]:
            best = (key, cards)
    return best[1][0] if best and best[1] else ""
