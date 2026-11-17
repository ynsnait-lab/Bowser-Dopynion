"""Assemblage d'une stratégie complète (responsable : Younes, intégrateur).

Une stratégie = phase Action (actions.py) + achats. Pour chaque achat :
0. tout à la fin, avec 8 pièces : Province ou pas, au calcul de nos chances (en duel : duel.duel_buy ;
   à 3 et 4 joueurs : la fin de partie jouée d'avance, lookahead.lookahead_buy) ;
1. une Province si on a 8 pièces et que la fin de partie l'autorise (endgame.province_ok) ;
2. sinon la carte qui arrête la partie en vidant une 3ᵉ pile, si on gagne alors (endgame.pile_finish) ;
3. sinon une carte Victoire si la fin de partie la réclame (endgame.endgame_buy) ;
4. sinon une carte d'économie (economy.economy_buy).

Chaque brique a son fichier et son responsable : on les améliore en parallèle
sans conflit, et on les assemble ici. Les réglages se cherchent en simulation
(outils/reglage.py) et se valident au championnat local (outils/arbitre_local.py).
"""

from dataclasses import dataclass, field, replace

from bot.strategy.actions import choose_action
from bot.strategy.base import END_TURN, Decision, Strategy, register
from bot.strategy.duel import duel_buy
from bot.strategy.economy import Economy, economy_buy
from bot.strategy.endgame import Endgame, endgame_buy, pile_finish, province_ok
from bot.strategy.lookahead import lookahead_buy
from bot.strategy.view import View


@dataclass(frozen=True)
class Plan:
    economy: Economy = field(default_factory=Economy)
    endgame: Endgame = field(default_factory=Endgame)
    play_actions: bool = True
    hireling_first: bool = False  # Recrue jouée avant la Sorcière, quand on n'a qu'une action


def buy_choice(view: View, money: int, plan: Plan) -> str | None:
    """Carte à acheter avec `money` pièces (None : on n'achète rien)."""
    decided = duel_buy(view, money, plan.endgame)
    if decided is None:
        decided = lookahead_buy(view, money, plan.endgame)
    if decided is not None:
        return decided or economy_buy(view, money, plan.economy)
    if money >= 8 and view.available("province") and province_ok(view, money, plan.endgame):
        return "province"
    return (
        pile_finish(view, money, plan.endgame)
        or endgame_buy(view, money, plan.endgame)
        or economy_buy(view, money, plan.economy)
    )


def plan_strategy(plan: Plan) -> Strategy:
    """Stratégie qui joue ses cartes Action puis achète selon `plan`."""

    def strategy(view: View) -> Decision:
        if plan.play_actions:
            card = choose_action(view, plan.hireling_first)
            if card is not None:
                return Decision("ACTION", card)
        if view.buys_left <= 0:
            return Decision(END_TURN)
        card = buy_choice(view, view.money, plan)
        return Decision("BUY", card) if card else Decision(END_TURN)

    return strategy


def by_players(plans: dict[int, Plan]) -> Strategy:
    """Stratégie qui change de réglage selon le nombre de joueurs à la table.

    On prend le réglage de la plus grande taille de table qui ne dépasse pas la nôtre
    (sinon le plus petit) : avec {2: A, 4: B}, A à 2 et 3 joueurs, B à 4 joueurs et plus.
    """
    strategies = {players: plan_strategy(plan) for players, plan in plans.items()}

    def strategy(view: View) -> Decision:
        sizes = [players for players in strategies if players <= view.players]
        return strategies[max(sizes) if sizes else min(strategies)](view)

    return strategy


BIG_MONEY = Plan(play_actions=False)
SMITHY_BM = Plan(economy=Economy(smithies=2))

# À toutes les tailles de table : un Domaine quand les Duchés sont épuisés, et la fin de
# partie sur les piles dès qu'elle nous fait gagner (vu dans une partie contre BigSmithy, 14/10).
PILE_RULES = {"estate_without_duchy": True, "finish_on_piles": True}

# Stratégie de l'équipe : un réglage par taille de table, re-cherché en parties appariées
# (outils/comparer.py --apparie) quand le site est passé au Royaume du 26/10 (Sorcière, Recrue,
# Chambre du conseil, Village agricole, Rivage lointain), puis à celui du 27/10 (Milice, Bandit,
# Bureaucrate, Chancelier, Jardins) : chiffres et explications dans docs/strategie.md.
# La fin de partie est celle d'avant (GROUPE3_V7). P = Provinces restantes.
GROUPE3 = {
    # En duel : 3 Sorcières avant tout (la 1ʳᵉ même avec 6 ou 7 pièces), 1 Recrue avec 6 pièces
    # avant l'Or (une autre dès qu'elle est jouée), 1 Bandit, 2 Marchés, 2 Festivals, 1 Milice,
    # 2 Villages agricoles (pour jouer Recrue, Sorcière, Bandit et Milice dans le même tour) ;
    # plus de Forgeron ni de Laboratoire. La Recrue se joue avant la Sorcière. Depuis le moteur 0.9.4
    # (8 Provinces en duel) : un seul Or avant la première Province, et un Domaine avec 2 pièces dès P <= 4.
    2: Plan(
        economy=Economy(
            witches=3,
            witches_over_gold=1,
            hirelings=1,
            bandits=1,
            markets=2,
            festivals=2,
            militias=1,
            farmingvillages=2,
            councilrooms=1,  # 16/11 : +0,5 à +0,7 point sur 3 séries de parties
        ),
        endgame=Endgame(estate_with_2_at=4, golds_before_province=1, duel_at=2, ties="premier", **PILE_RULES),
        hireling_first=True,
    ),
    # À 3 : 2 Sorcières, 1 Recrue (jouée avant la Sorcière), 1 Bandit, 2 Laboratoires (16/11), 1 Marché,
    # 1 Festival, 1 Milice ; plus de Forgeron. Les points un cran plus tôt qu'avant.
    3: Plan(
        economy=Economy(
            labs=2, markets=1, festivals=1, witches=2, witches_over_gold=1, hirelings=1, bandits=1, militias=1
        ),
        endgame=Endgame(
            shift_3_players=1,
            duchy_with_5_at=6,
            duchy_with_6_at=6,
            estate_with_3_at=3,
            estate_with_2_at=4,
            golds_before_province=2,
            finish_share=0.5,
            lookahead_at=2,
            ties="premier",
            **PILE_RULES,
        ),
        hireling_first=True,
    ),
    # À 4 : 1 seule Sorcière (même avec 6 ou 7 pièces), 1 Recrue, 1 Bandit, 1 Laboratoire et 2 Festivals
    # (16/11), 1 Marché, 1 Milice ; plus de Forgeron ; les points un cran plus tôt qu'avant.
    4: Plan(
        economy=Economy(
            labs=1, markets=1, festivals=2, witches=1, witches_over_gold=1, hirelings=1, bandits=1, militias=1
        ),
        endgame=Endgame(
            duchy_with_5_at=9,
            duchy_with_6_at=6,
            estate_with_3_at=3,
            estate_with_2_at=7,
            shift_4_players=1,
            golds_before_province=1,
            finish_share=0.5,
            lookahead_at=2,
            ties="premier",
            **PILE_RULES,
        ),
        hireling_first=True,
    ),
}

# Versions précédentes, gardées pour mesurer nos progrès. Celle du 16/11 à 14h (sans Chambre du conseil
# en duel, avec 1 seul Labo à 3 joueurs, aucun à 4) :
GROUPE3_V10 = {
    2: replace(GROUPE3[2], economy=replace(GROUPE3[2].economy, councilrooms=0)),
    3: replace(GROUPE3[3], economy=replace(GROUPE3[3].economy, labs=0)),
    4: replace(GROUPE3[4], economy=replace(GROUPE3[4].economy, labs=0, festivals=1)),
}
# Celle du 27/10 au soir, avant le moteur
# 0.9.4 et la règle des égalités du site (un demi-duel en duel, rien de visé à 3 et 4) :
GROUPE3_V9 = {
    2: replace(
        GROUPE3[2], endgame=replace(GROUPE3[2].endgame, estate_with_2_at=2, golds_before_province=2, ties="demi")
    ),
    3: replace(GROUPE3[3], endgame=replace(GROUPE3[3].endgame, ties="inconnue")),
    4: replace(GROUPE3[4], endgame=replace(GROUPE3[4].endgame, ties="inconnue")),
}
# Celle du 27/10 après-midi, sans les cartes du 27/10 (ni Milice ni Bandit) :
GROUPE3_V8 = {
    2: replace(GROUPE3_V9[2], economy=Economy(witches=3, witches_over_gold=1, hirelings=1, festivals=2)),
    3: replace(
        GROUPE3_V9[3],
        economy=Economy(markets=1, festivals=1, witches=2, witches_over_gold=1, hirelings=1),
        endgame=replace(GROUPE3_V9[3].endgame, shift_3_players=0),
    ),
    4: replace(GROUPE3_V9[4], economy=Economy(markets=1, witches=2, witches_over_gold=1, hirelings=1)),
}
# Celle du 27/10 au matin, sans les cartes du Royaume du 26/10 (elle n'achète ni Sorcière ni Recrue) :
GROUPE3_V7 = {
    # En duel : 2 Forgerons dès le début, puis 1 Laboratoire et 2 Festivals ; pas de Province
    # avant d'avoir 2 Ors (tant que P > 4) ; des Domaines seulement à la toute fin. Avec 8 pièces
    # quand P <= 2 : Province ou Duché au calcul de nos chances, d'après les cartes de l'adversaire.
    # Une égalité y compte pour un demi-duel : mesuré gagnant (ou nul) quelle que soit la vraie
    # règle du site (question 8), en attendant de la connaître.
    2: Plan(
        economy=Economy(smithies=2, cards_per_smithy=6, labs=1, festivals=2),
        endgame=Endgame(estate_with_2_at=2, golds_before_province=2, duel_at=2, ties="demi", **PILE_RULES),
    ),
    # À 3 : le 2ᵉ Forgeron à 17 cartes ; 2 Ors avant la première Province, comme en duel ;
    # des points tôt : Duché dès que P <= 6, Domaine avec 3 ou 4 pièces dès que P <= 3.
    # On finit la partie dès qu'on gagne au moins la moitié de nos duels, même 2ᵉ. Avec 8 pièces
    # quand P <= 2 : Province ou pas, en jouant la fin de partie d'avance (strategy/lookahead.py).
    3: Plan(
        economy=Economy(smithies=2, cards_per_smithy=17),
        endgame=Endgame(
            duchy_with_5_at=6,
            duchy_with_6_at=6,
            estate_with_3_at=3,
            estate_with_2_at=4,
            golds_before_province=2,
            finish_share=0.5,
            lookahead_at=2,
            **PILE_RULES,
        ),
    ),
    # À 4 : les Provinces partent vite, on prend des points bien plus tôt :
    # Duché avec 5 pièces dès que P <= 9, avec 6 ou 7 pièces dès que P <= 6 ; 1 Or d'abord.
    # Avec 8 pièces quand P <= 2, comme à 3 : la fin de partie jouée d'avance.
    4: Plan(
        economy=Economy(smithies=2, cards_per_smithy=17),
        endgame=Endgame(
            duchy_with_5_at=9,
            duchy_with_6_at=6,
            estate_with_3_at=3,
            estate_with_2_at=7,
            golds_before_province=1,
            finish_share=0.5,
            lookahead_at=2,
            **PILE_RULES,
        ),
    ),
}

# Et avant : celle du 12/10, celle du 13/10 (sans les règles des piles), celle du 20/10 (avant
# le re-réglage apparié), celle du 26/10 (sans le calcul de risque en duel), celle du 26/10 au
# soir (sans la fin de partie jouée d'avance à 3 et 4 joueurs) et celle du 27/10 au matin (sans
# l'égalité comptée pour un demi-duel en duel).
GROUPE3_V1 = Plan(
    economy=Economy(smithies=2, cards_per_smithy=17),
    endgame=Endgame(duchy_with_6_at=2, shift_4_players=2),
)
GROUPE3_V3 = {
    2: Plan(
        economy=Economy(smithies=2, cards_per_smithy=6, festivals=1),
        endgame=Endgame(estate_with_2_at=2, golds_before_province=2, **PILE_RULES),
    ),
    3: Plan(
        economy=Economy(smithies=2, cards_per_smithy=17),
        endgame=Endgame(duchy_with_6_at=5, finish_share=0.5, **PILE_RULES),
    ),
    4: Plan(
        economy=Economy(smithies=2, cards_per_smithy=17),
        endgame=Endgame(
            duchy_with_5_at=8, duchy_with_6_at=5, estate_with_3_at=4, estate_with_2_at=6, finish_share=0.5, **PILE_RULES
        ),
    ),
}
GROUPE3_V6 = {
    players: replace(plan, endgame=replace(plan.endgame, ties="inconnue")) for players, plan in GROUPE3_V7.items()
}
GROUPE3_V5 = {
    players: replace(plan, endgame=replace(plan.endgame, lookahead_at=0)) for players, plan in GROUPE3_V6.items()
}
GROUPE3_V4 = {**GROUPE3_V5, 2: replace(GROUPE3_V5[2], endgame=replace(GROUPE3_V5[2].endgame, duel_at=0))}
GROUPE3_V2 = {
    players: replace(plan, endgame=replace(plan.endgame, estate_without_duchy=False, finish_on_piles=False))
    for players, plan in GROUPE3_V3.items()
}

register("groupe3", by_players(GROUPE3))
register("groupe3_v1", plan_strategy(GROUPE3_V1))
register("groupe3_v2", by_players(GROUPE3_V2))
register("groupe3_v3", by_players(GROUPE3_V3))
register("groupe3_v4", by_players(GROUPE3_V4))
register("groupe3_v5", by_players(GROUPE3_V5))
register("groupe3_v6", by_players(GROUPE3_V6))
register("groupe3_v7", by_players(GROUPE3_V7))
register("groupe3_v8", by_players(GROUPE3_V8))
register("groupe3_v9", by_players(GROUPE3_V9))
register("groupe3_v10", by_players(GROUPE3_V10))
register("smithy_bm", plan_strategy(SMITHY_BM))
register("big_money", plan_strategy(BIG_MONEY))
