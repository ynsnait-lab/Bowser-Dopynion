"""Bac à sable de Younes : idées en cours d'essai.

Ce fichier est chargé automatiquement : les stratégies enregistrées ici apparaissent dans
le simulateur, dans outils/comparer.py et au championnat local (outils/arbitre_local.py).
Les candidats du 13/10 qui ont gagné sont devenus GROUPE3 (plans.py) ; les chiffres de
tous les essais sont dans docs/strategie.md.
"""

from bot.strategy import Economy, Endgame, Plan, plan_strategy, register

# Un « moteur » : Villages + Forgerons + Laboratoires + Marchés pour piocher tout son deck
# et acheter deux fois par tour. Sur le papier, intéressant quand les parties sont longues
# (12 Provinces à 2 joueurs). En simulation, il perd contre le simple Big Money + Forgerons.
register(
    "younes_moteur",
    plan_strategy(
        Plan(
            economy=Economy(
                smithies=3,
                cards_per_smithy=8,
                villages=2,
                labs=2,
                markets=1,
                festivals=1,
                kingdom_while_provinces_above=4,
            ),
        ),
    ),
)

# Le meilleur réglage UNIQUE (le même à 2, 3 et 4 joueurs) trouvé par outils/reglage.py.
# Gardé pour comparaison : un réglage par taille de table (GROUPE3) fait mieux à 2 et à 4.
register(
    "younes_unique",
    plan_strategy(
        Plan(
            economy=Economy(smithies=2, cards_per_smithy=17, labs=2),
            endgame=Endgame(duchy_with_6_at=5, shift_4_players=2, golds_before_province=2),
        ),
    ),
)
