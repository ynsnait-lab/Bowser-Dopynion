"""Fin de partie : quand prendre des cartes Victoire (responsable : Jean-Eudes).

P = Provinces restantes. La partie s'arrête quand les Provinces sont épuisées :
prendre la dernière (ou les deux dernières d'un coup) n'est intéressant que si le
score final nous arrange. Le classement ELO compte chaque adversaire de la table
comme un duel : à 3 ou 4 joueurs, finir 2ᵉ en battant les autres rapporte des points,
même derrière le meneur (`finish_share`). Les seuils « quand P <= N » peuvent s'avancer
avec le nombre de joueurs (shift) : à 4, les Provinces partent environ deux fois plus
vite qu'à 2.

La partie s'arrête aussi quand 3 piles de la réserve sont vides. À 4 joueurs, les
12 Duchés et les 12 Domaines partent souvent avant la fin : il faut alors un Domaine
à la place du Duché (`estate_without_duchy`), et, si 2 piles sont déjà vides, vider
la 3ᵉ arrête la partie : on le fait dès que ça nous donne la victoire (`finish_on_piles`).
"""

from dataclasses import dataclass

from bot.cards import info
from bot.strategy.view import View

PROVINCE_POINTS = 6


@dataclass(frozen=True)
class Endgame:
    duchy_with_5_at: int = 5  # Duché avec exactement 5 pièces quand P <= N
    duchy_with_6_at: int = 4  # Duché avec 6 pièces ou plus (Province refusée) quand P <= N
    estate_with_3_at: int = 2  # Domaine avec 3 ou 4 pièces quand P <= N
    estate_with_2_at: int = 3  # Domaine avec exactement 2 pièces quand P <= N
    shift_3_players: int = 0  # à 3 joueurs, seuils avancés de N Provinces
    shift_4_players: int = 0  # à 4 joueurs, seuils avancés de N Provinces
    golds_before_province: int = 0  # Or plutôt que Province tant qu'on a moins de N Ors (si P > 4)
    protect_last_province: bool = True  # pas de dernière Province si la fin de partie nous fait perdre
    # Finir la partie seulement si on gagne au moins cette part de nos duels (1 par adversaire
    # battu, 0,5 par égalité) : 1.0 = battre tout le monde ; 0.5 = la moitié (à 2 : l'égalité suffit).
    finish_share: float = 1.0
    penultimate_rule: bool = False  # pas d'avant-dernière Province si l'adversaire peut finir devant
    estate_without_duchy: bool = False  # plus de Duchés alors qu'on en voulait un : un Domaine à la place
    finish_on_piles: bool = False  # 2 piles vides : vider la 3ᵉ (fin de partie) si on gagne alors
    # En duel, quand P <= N : l'achat avec 8 pièces ou plus se décide au calcul de nos chances
    # de gagner, d'après les cartes de l'adversaire (strategy/duel.py). 0 = jamais.
    duel_at: int = 0
    # ... une égalité qu'on provoque en finissant la partie y compte pour tant de victoire. 0 tant
    # qu'on ne sait pas comment le site compte les égalités (question 8) : on ne la vise jamais.
    duel_tie: float = 0.0
    # Comment le site compte une égalité (question 8) : "inconnue" (on fait comme avant : jamais
    # d'égalité visée en duel, un demi-duel à 3 et 4), "demi" (un demi-duel), "premier" (à égalité,
    # le joueur qui a joué le plus tôt passe devant), "dernier" (celui qui a joué le plus tard).
    ties: str = "inconnue"
    # À 3 ou 4 joueurs, quand P <= N : l'achat avec 8 pièces ou plus se décide en jouant la fin de
    # partie d'avance, `lookahead_games` fois par achat comparé (strategy/lookahead.py). 0 = jamais.
    lookahead_at: int = 0
    lookahead_games: int = 300


def shift(view: View, end: Endgame) -> int:
    if view.players >= 4:
        return end.shift_4_players
    if view.players == 3:
        return end.shift_3_players
    return 0


def tie_result(rule: str, me: int | None, other: int | None, unknown: float) -> float:
    """Ce que nous rapporte un duel à égalité de points, selon la règle du site et l'ordre de jeu
    (`me`, `other` : places à la table, 0 = premier à jouer). Règle ou places inconnues : `unknown`."""
    if rule == "demi":
        return 0.5
    if rule in ("premier", "dernier") and me is not None and other is not None:
        return 1.0 if (me < other) == (rule == "premier") else 0.0
    return unknown


def opponent_seats(view: View) -> list[int | None]:
    """Place à la table de chaque adversaire, dans l'ordre de `view.margins`."""
    if view.seat is None or not view.margins:
        return [None] * max(1, len(view.margins))
    return [j if j < view.seat else j + 1 for j in range(len(view.margins))]


def finishing_pays(view: View, points: int, end: Endgame) -> bool:
    """Finir la partie tout de suite, avec `points` de plus : gagne-t-on assez de duels ?"""
    margins = view.margins or ((view.lead,) if view.lead is not None else ())
    if not margins:
        return True  # scores inconnus : on prend les points
    seats = opponent_seats(view)
    duels = sum(
        1.0 if m + points > 0 else tie_result(end.ties, view.seat, seat, 0.5) if m + points == 0 else 0.0
        for m, seat in zip(margins, seats, strict=False)
    )
    return duels >= end.finish_share * len(margins)


def province_ok(view: View, money: int, end: Endgame) -> bool:
    """Prendre une Province maintenant est-il une bonne idée ?"""
    provinces, lead = view.provinces, view.lead
    if provinces == 2 and view.buys_left >= 2 and money >= 16:
        return finishing_pays(view, 2 * PROVINCE_POINTS, end)  # les deux dernières d'un coup
    if end.protect_last_province and provinces == 1 and not finishing_pays(view, PROVINCE_POINTS, end):
        return False  # la dernière Province finirait la partie en nous faisant perdre trop de duels
    if end.penultimate_rule and provinces == 2 and lead is not None and lead <= 0:
        return False  # l'adversaire pourrait prendre la dernière et finir devant
    if provinces > 4 and view.deck["gold"] < end.golds_before_province and view.available("gold"):
        return False  # d'abord de l'Or : l'économie avant les points
    return True


def endgame_buy(view: View, money: int, end: Endgame) -> str | None:
    """Carte Victoire réclamée par la fin de partie (None : on laisse l'économie décider).

    Chaque seuil vaut pour sa tranche d'argent : 6 pièces et plus, exactement 5, 3 ou 4, exactement 2.
    """
    p = view.provinces - shift(view, end)  # à plus de joueurs, on fait comme s'il en restait moins
    if money >= 6:
        card, threshold = "duchy", end.duchy_with_6_at
    elif money == 5:
        card, threshold = "duchy", end.duchy_with_5_at
    elif money >= 3:
        card, threshold = "estate", end.estate_with_3_at
    elif money == 2:
        card, threshold = "estate", end.estate_with_2_at
    else:
        return None
    if p > threshold:
        return None
    if card == "duchy" and not view.available("duchy") and end.estate_without_duchy:
        card = "estate"  # Duchés épuisés : un Domaine, c'est toujours un point de plus
    return card if view.available(card) else None


def wins_if_finished(view: View, points: int, rule: str = "inconnue") -> bool:
    """Finir la partie tout de suite, avec `points` de plus : bat-on tout le monde (une égalité ne
    compte que si la règle du site nous classe devant) ? Scores inconnus : non, jamais à l'aveugle."""
    margins = view.margins or ((view.lead,) if view.lead is not None else ())
    seats = opponent_seats(view)
    return bool(margins) and all(
        m + points > 0 or (m + points == 0 and tie_result(rule, view.seat, seat, 0.0) == 1.0)
        for m, seat in zip(margins, seats, strict=False)
    )


def pile_finish(view: View, money: int, end: Endgame) -> str | None:
    """2 piles déjà vides : la dernière carte d'une 3ᵉ pile arrête la partie. On la prend
    si on gagne alors la partie, la plus rentable en points d'abord, puis la moins chère."""
    if not end.finish_on_piles or view.empty_piles < 2:
        return None
    last_cards = [
        card for card, quantity in view.stock.items() if quantity == 1 and _known(card) and info(card).cost <= money
    ]
    for card in sorted(last_cards, key=lambda c: (-info(c).victory_points, info(c).cost, c)):
        if wins_if_finished(view, info(card).victory_points, end.ties):
            return card
    return None


def _known(card: str) -> bool:
    """Carte dont on connaît la fiche (une carte inconnue a un coût de 0 : on ne l'achète pas)."""
    card_info = info(card)
    return card_info.is_action or card_info.is_treasure or card_info.is_victory
