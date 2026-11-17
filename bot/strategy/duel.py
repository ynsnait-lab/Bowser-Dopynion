"""Fin de partie en duel : décider avec le vrai risque plutôt qu'avec des seuils fixes (responsable : Jean-Eudes).

En duel, ce qui disparaît de la réserve entre deux de nos décisions, c'est l'adversaire qui l'a
acheté (bot/memory.py) : avec son jeu de départ, on connaît donc TOUTES ses cartes. On en tire ses
chances de faire 8 pièces (ou 5, ou 16 avec 2 achats) à son prochain tour, pareil pour nous, puis on
calcule nos chances de gagner pour chaque achat possible, en jouant la fin de partie jusqu'au bout :
- nous : on prend toujours le plus de points possible, en choisissant combien de Provinces ;
- l'adversaire : un bot « Big Money » classique, Province dès 8 pièces (la dernière seulement si
  elle le fait gagner), Duché avec 5 à 7 pièces vers la fin, Domaine tout à la fin.

Ce que ça change en pratique (P = Provinces restantes, réglé à P <= 2 en duel) : derrière au score,
on ne prend plus l'avant-dernière Province si l'adversaire a de bonnes chances de prendre la dernière
et de finir devant ; on prend un Duché et on garde la main sur la fin de partie.
"""

import random
from collections import Counter
from functools import lru_cache

from bot.cards import STARTING_DECK, info, money_value
from bot.strategy.actions import action_priority
from bot.strategy.endgame import Endgame, opponent_seats, tie_result
from bot.strategy.view import View

SAMPLES = 400  # mains tirées pour estimer les chances d'un deck
DRAWN = 15  # cartes tirées par main au plus : 5, plus la pioche des Actions
MONEY_CAP = 16  # au-delà, rien de plus à acheter (2 Provinces)
LEAD_CAP = 30  # avance au-delà de laquelle la partie est jouée
PROVINCE, DUCHY, ESTATE = 6, 3, 1  # points de victoire

Odds = tuple[tuple[int, int, float], ...]  # (argent, achats, probabilité)
Table = list[list[float]]  # table[Provinces restantes][avance + LEAD_CAP] = nos chances de gagner
LEADS = range(-LEAD_CAP, LEAD_CAP + 1)


def deck_key(deck: Counter) -> tuple[tuple[str, int], ...]:
    return tuple(sorted((card, qty) for card, qty in deck.items() if qty > 0))


@lru_cache(maxsize=2048)
def turn_odds(cards: tuple[tuple[str, int], ...]) -> Odds:
    """Argent et achats d'un tour au hasard avec ce deck : 5 cartes, puis les Actions jouées
    comme le fait notre bot. Tirage avec son propre générateur, réglé par le deck : le résultat
    est toujours le même pour un même deck, et le hasard du jeu n'est pas touché."""
    deck = [card for card, qty in cards for _ in range(qty)]
    rng = random.Random(repr(cards))
    counts: Counter = Counter()
    for _ in range(SAMPLES):
        drawn = rng.sample(deck, min(len(deck), DRAWN))  # le dessus du deck mélangé
        hand, pile = drawn[:5], drawn[5:]
        actions, buys, money = 1, 1, 0
        while actions > 0:
            playable = [card for card in hand if info(card).is_simple_action]
            if not playable:
                break
            card = max(playable, key=action_priority)
            hand.remove(card)
            effect = info(card)
            actions += effect.plus_actions - 1
            buys += effect.plus_buys
            money += effect.plus_money
            hand += pile[: effect.plus_cards]
            pile = pile[effect.plus_cards :]
        money += sum(money_value(card) for card in hand)
        counts[min(money, MONEY_CAP), min(buys, 2)] += 1
    return tuple((money, buys, n / SAMPLES) for (money, buys), n in sorted(counts.items()))


def our_options(money: int, buys: int, provinces: int) -> list[tuple[int, int]]:
    """Nos achats possibles en (Provinces prises, points gagnés) : pour chaque nombre de
    Provinces, le plus de points possible avec le reste (Duché, sinon Domaine)."""
    options = []
    for taken in range(min(buys, provinces, money // 8) + 1):
        left, points = money - 8 * taken, PROVINCE * taken
        for _ in range(buys - taken):
            if left >= 5:
                points, left = points + DUCHY, left - 5
            elif left >= 2:
                points, left = points + ESTATE, left - 2
        options.append((taken, points))
    return options


def their_buys(money: int, buys: int, provinces: int, their_lead: int) -> tuple[int, int]:
    """Ce qu'achète un adversaire « Big Money » (réglages de fin de partie par défaut) :
    (Provinces prises, points gagnés)."""
    taken = points = 0
    for _ in range(buys):
        left = provinces - taken
        if money >= 8 and left > 0 and (left > 1 or their_lead + points + PROVINCE > 0):
            taken, points, money = taken + 1, points + PROVINCE, money - 8
        elif money >= 5 and (left <= 4 or (money == 5 and left <= 5)):
            points, money = points + DUCHY, money - 5
        elif (money >= 3 and left <= 2) or (money == 2 and left <= 3):
            points, money = points + ESTATE, money - 2
        else:
            break
    return taken, points


def _index(lead: int) -> int:
    return max(-LEAD_CAP, min(LEAD_CAP, lead)) + LEAD_CAP


def chances_after(table: Table, provinces: int, lead: int, tie: float) -> float:
    """Nos chances avec `provinces` Provinces restantes et cette avance. Plus de Province : la
    partie est finie, gagnée, perdue, ou nulle (elle compte alors pour `tie` victoire)."""
    if provinces <= 0:
        return 1.0 if lead > 0 else tie if lead == 0 else 0.0
    return table[provinces][_index(lead)]


def _with_provinces(yours: Table, level: int, options: tuple, lead: int, tie: float) -> float:
    """Nos chances avec la meilleure option qui prend au moins une Province (-1 : aucune)."""
    return max((chances_after(yours, level - t, lead + p, tie) for t, p in options if t), default=-1.0)


@lru_cache(maxsize=256)
def win_chances(provinces: int, ours: Odds, theirs: Odds, tie: float) -> tuple[Table, Table]:
    """Nos chances de gagner jusqu'à `provinces` Provinces restantes, selon l'avance : `mine`
    quand c'est à nous d'acheter, `yours` quand c'est à l'adversaire.

    On remonte de 1 Province restante à `provinces` : prendre une Province fait descendre d'un
    étage, déjà calculé (des chances connues) ; un tour sans Province reste au même étage, qu'on
    calcule en répétant jusqu'à ce que les chances ne bougent plus. `tie` ne compte que quand
    c'est nous qui finissons : l'adversaire ne prend la dernière Province que pour gagner.
    """
    mine: Table = [[]]
    yours: Table = [[]]
    for level in range(1, provinces + 1):
        # Notre tour : pour chaque main possible, la meilleure option avec Province(s) (chances
        # connues) ou celle sans Province (chances au tour de l'adversaire, même étage).
        groups: Counter = Counter()
        for money, buys, prob in ours:
            groups[tuple(our_options(money, buys, level))] += prob
        our_turn = []
        for options, prob in groups.items():
            stay = options[0][1]  # points sans Province
            best = [_with_provinces(yours, level, options, lead, tie) for lead in LEADS]
            our_turn.append((prob, best, [_index(lead + stay) for lead in LEADS]))
        # Tour de l'adversaire : part connue (il a pris une Province) + renvois au même étage.
        known = [0.0] * len(LEADS)
        links: list[Counter] = [Counter() for _ in LEADS]
        for i, lead in enumerate(LEADS):
            for money, buys, prob in theirs:
                taken, points = their_buys(money, buys, level, -lead)
                if taken:
                    known[i] += prob * chances_after(mine, level - taken, lead - points, tie)
                else:
                    links[i][_index(lead - points)] += prob
        their_turn = [list(link.items()) for link in links]
        m, y = [0.5] * len(LEADS), [0.5] * len(LEADS)
        for _ in range(1000):
            change = 0.0
            for i in range(len(LEADS)):
                value = known[i] + sum(prob * m[j] for j, prob in their_turn[i])
                change, y[i] = max(change, abs(value - y[i])), value
            for i in range(len(LEADS)):
                value = sum(prob * max(best[i], y[stay[i]]) for prob, best, stay in our_turn)
                change, m[i] = max(change, abs(value - m[i])), value
            if change < 1e-6:
                break
        mine.append(m)
        yours.append(y)
    return mine, yours


def duel_buy(view: View, money: int, end: Endgame) -> str | None:
    """Carte Victoire choisie au calcul de nos chances ("" : aucune), ou None quand le calcul ne
    s'applique pas : pas en duel, moins de 8 pièces, trop tôt (P > end.duel_at), scores ou cartes
    adverses inconnus."""
    provinces = view.provinces
    if view.players != 2 or money < 8 or not 0 < provinces <= end.duel_at:
        return None
    if view.lead is None or view.others_bought is None:
        return None
    ours = turn_odds(deck_key(view.deck))
    theirs = turn_odds(deck_key(Counter(STARTING_DECK) + view.others_bought))
    # Règle connue mais places inconnues : une chance sur deux de jouer avant l'adversaire.
    unknown = end.duel_tie if end.ties == "inconnue" else 0.5
    tie = tie_result(end.ties, view.seat, opponent_seats(view)[0], unknown)
    _, yours = win_chances(provinces, ours, theirs, tie)

    def chances(option: tuple[int, int]) -> tuple[float, int]:
        taken, points = option
        return round(chances_after(yours, provinces - taken, view.lead + points, tie), 9), points

    taken, points = max(our_options(money, min(view.buys_left, 2), provinces), key=chances)
    if taken:
        return "province"
    card = "duchy" if money >= 5 and view.available("duchy") else "estate"
    return card if points and view.available(card) else ""
