"""Achats d'économie : enrichir le deck pour pouvoir acheter des Provinces (responsable : Pauline).

Appelé seulement quand la fin de partie (endgame.py) ne réclame pas de carte Victoire.
Principe « Big Money » : de l'argent (Argent, Or) et quelques cartes qui piochent.
Depuis le 26/10, le Royaume du site change à chaque partie (10 cartes parmi 16 depuis le 27/10) : chaque carte
n'est achetée que si elle est dans la réserve, sinon on passe à la suivante. La Sorcière donne
une Malédiction (-1 point) à chaque adversaire : on n'en achète plus quand elles sont épuisées.
P = Provinces restantes.
"""

from collections import Counter
from dataclasses import dataclass

from bot.strategy.view import View


@dataclass(frozen=True)
class Economy:
    smithies: int = 0  # Forgerons au maximum (achetés avec 4 ou 5 pièces)
    cards_per_smithy: int = 11  # un Forgeron de plus autorisé par tranche de N cartes
    labs: int = 0  # Laboratoires au maximum (5 pièces)
    markets: int = 0  # Marchés au maximum (5 pièces)
    festivals: int = 0  # Festivals au maximum (5 pièces)
    villages: int = 0  # Villages au maximum (3 pièces), seulement à partir de 2 Forgerons
    kingdom_while_provinces_above: int = 6  # plus de carte Royaume à 5 pièces quand P <= N
    witches: int = 0  # Sorcières au maximum (5 pièces), avant toute autre carte Royaume
    witches_over_gold: int = 0  # ... dont les N premières même avec 6 ou 7 pièces, au lieu d'un Or
    hirelings: int = 0  # Recrues au maximum (6 pièces), avant l'Or
    councilrooms: int = 0  # Chambres du conseil au maximum (5 pièces), après Labos, Marchés, Festivals
    farmingvillages: int = 0  # Villages agricoles au maximum (4 pièces), avant le Forgeron
    bandits: int = 0  # Bandits au maximum (5 pièces : un Or pour nous, un trésor écarté chez chaque adversaire)
    militias: int = 0  # Milices au maximum (4 pièces : +2 pièces, chaque adversaire défausse jusqu'à 3 cartes)
    # Cartes arrivées sur le site le 16/11 :
    magnates: int = 0  # Magnats au maximum (5 pièces : +1 carte par Trésor en main), avant les Laboratoires
    libraries: int = 0  # Bibliothèques au maximum (5 pièces : piocher jusqu'à 7 cartes en main), après les Magnats
    adventurers: int = 0  # Aventuriers au maximum (6 pièces : piocher jusqu'à 2 Trésors), après la Recrue, avant l'Or
    fortunetellers: int = 0  # Diseuses de bonne aventure au maximum (3 pièces : +2 pièces), avant l'Argent
    cellars: int = 0  # Caves au maximum (2 pièces : défausser les cartes mortes pour repiocher), avec 2 pièces
    workshops: int = 0  # Ateliers au maximum (3 pièces : recevoir une carte jusqu'à 4), avec 3 ou 4 pièces


def smithy_allowed(deck: Counter, eco: Economy) -> bool:
    """Un premier Forgeron tout de suite, puis un de plus par tranche de `cards_per_smithy` cartes."""
    allowed = min(eco.smithies, 1 + sum(deck.values()) // eco.cards_per_smithy)
    return deck["smithy"] < allowed


def economy_buy(view: View, money: int, eco: Economy) -> str | None:
    """Carte d'économie à acheter avec `money` pièces (None : rien d'utile)."""
    witch_wanted = view.available("curse") and view.available("witch")
    if money >= 6:
        if witch_wanted and view.deck["witch"] < min(eco.witches_over_gold, eco.witches):
            return "witch"
        if view.deck["hireling"] < eco.hirelings and view.available("hireling"):
            return "hireling"
        if view.deck["adventurer"] < eco.adventurers and view.available("adventurer"):
            return "adventurer"
        if view.available("gold"):
            return "gold"
    if money >= 5 and witch_wanted and view.deck["witch"] < eco.witches:
        return "witch"
    if money >= 5 and view.deck["bandit"] < eco.bandits and view.available("bandit"):
        return "bandit"
    if money >= 5 and view.provinces > eco.kingdom_while_provinces_above:
        draws = (("magnate", eco.magnates), ("library", eco.libraries))
        kingdom = (("laboratory", eco.labs), ("market", eco.markets), ("festival", eco.festivals))
        for card, limit in (*draws, *kingdom, ("councilroom", eco.councilrooms)):
            if view.deck[card] < limit and view.available(card):
                return card
    if money >= 4 and view.deck["militia"] < eco.militias and view.available("militia"):
        return "militia"
    if money >= 4 and view.deck["farmingvillage"] < eco.farmingvillages and view.available("farmingvillage"):
        return "farmingvillage"
    if money >= 4 and smithy_allowed(view.deck, eco) and view.available("smithy"):
        return "smithy"
    if money >= 3:
        if view.deck["village"] < eco.villages and view.deck["smithy"] >= 2 and view.available("village"):
            return "village"
        if money <= 4 and view.deck["workshop"] < eco.workshops and view.available("workshop"):
            return "workshop"
        if view.deck["fortuneteller"] < eco.fortunetellers and view.available("fortuneteller"):
            return "fortuneteller"
        if view.available("silver"):
            return "silver"
    if money == 2 and view.deck["cellar"] < eco.cellars and view.available("cellar"):
        return "cellar"
    return None
