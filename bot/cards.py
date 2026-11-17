"""Ce que le bot sait des cartes : coût, valeur en pièces, type, effets.

On réutilise les fiches du moteur public `dopynion` pour rester aligné sur
les règles de l'arbitre. Si une carte est inconnue (nouvelle version du
moteur...), on renvoie une fiche neutre au lieu de planter : une carte
inconnue n'est jamais jouée.
"""

from dataclasses import dataclass
from functools import cache

try:
    from dopynion.cards import Card as _EngineCard
except Exception:  # noqa: BLE001 - le bot doit démarrer quoi qu'il arrive
    _EngineCard = None

# Jeu de départ constaté dans les parties de l'arbitre (08/10) : 7 Cuivres et 3 Domaines.
STARTING_DECK = {"copper": 7, "estate": 3}


# Cartes à effet spécial qui ne demandent AUCUN choix à celui qui les joue (lu dans le moteur 0.9.3) :
# les jouer est sans risque. Arrivées sur le site le 26/10. La Sorcière donne une Malédiction à
# chaque adversaire ; la Chambre du conseil fait piocher une carte à chacun d'eux ; la Recrue sort
# du jeu et fait piocher une carte de plus à chaque début de tour ; le Village agricole révèle des
# cartes jusqu'à un Trésor ou une Action ; le Rivage lointain fait recevoir un Domaine.
NO_CHOICE_EFFECTS = {"witch", "councilroom", "hireling", "farmingvillage", "distantshore"}  # 26/10
NO_CHOICE_EFFECTS |= {"militia", "bandit", "bureaucrat"}  # 27/10 : les adversaires choisissent, pas nous
# 16/11 : l'Aventurier pioche jusqu'à 2 Trésors, le Magnat une carte par Trésor en main, la Diseuse de
# bonne aventure fait défausser le dessus du deck des adversaires : aucun choix. La Bibliothèque (piocher
# jusqu'à 7 cartes) et la Cave (défausser pour repiocher) nous demandent un oui ou un non par carte, sur
# des routes auxquelles on répond toujours (bot/safety.py) : sans risque aussi.
NO_CHOICE_EFFECTS |= {"adventurer", "magnate", "fortuneteller", "library", "cellar"}
# Atelier (recevoir une carte coûtant jusqu'à 4) et Festin (s'écarter, recevoir une carte jusqu'à 5) :
# l'arbitre nous demande laquelle sur choose_card_to_receive_in_discard (confirmé par le prof le 16/11),
# et c'est notre stratégie d'achat qui choisit (bot/safety.py, choose_gain).
NO_CHOICE_EFFECTS |= {"workshop", "feast"}


@dataclass(frozen=True)
class CardInfo:
    name: str
    cost: int = 0
    money: int = 0
    victory_points: int = 0
    is_action: bool = False
    is_treasure: bool = False
    is_victory: bool = False
    plus_cards: int = 0
    plus_actions: int = 0
    plus_buys: int = 0
    plus_money: int = 0
    # Effet particulier quand on la joue (choix, attaque, pioche conditionnelle...).
    # Par défaut True : une carte qu'on ne connaît pas n'est jamais jouée.
    has_special_play_effect: bool = True

    @property
    def is_dead_in_hand(self) -> bool:
        """Carte qui ne sert à rien en main : Victoire pure ou Malédiction."""
        return self.is_victory and not (self.is_action or self.is_treasure)

    @property
    def is_simple_action(self) -> bool:
        """Carte Action aux effets fixes (+cartes, +actions, +achats, +argent) : sûre à jouer."""
        return self.is_action and not self.has_special_play_effect


@cache
def info(name: str) -> CardInfo:
    try:
        engine_card = _EngineCard.class_(name)
        if engine_card is _EngineCard:  # carte inconnue du moteur installé
            return CardInfo(name)
        return CardInfo(
            name=name,
            cost=engine_card.cost,
            money=engine_card.money,
            victory_points=engine_card.victory_points,
            is_action=engine_card.is_action,
            is_treasure=engine_card.is_treasure,
            is_victory=engine_card.is_victory,
            plus_cards=engine_card.more_cards_from_deck,
            plus_actions=engine_card.more_actions,
            plus_buys=engine_card.more_purchases,
            plus_money=engine_card.more_money,
            has_special_play_effect="_action" in vars(engine_card) and name not in NO_CHOICE_EFFECTS,
        )
    except Exception:  # noqa: BLE001
        return CardInfo(name)


def money_value(name: str) -> int:
    """Pièces qu'une carte en main nous permet de dépenser.

    L'Or maudit compte pour 0 : il vaut 3 pièces mais donne une Malédiction
    (-1 PV) quand on s'en sert. Le moteur le dépense en dernier, donc tant
    qu'on achète avec les autres trésors, il ne sert jamais.
    """
    if name == "cursedgold":
        return 0
    return info(name).money


def hand_money(hand: dict[str, int]) -> int:
    """Argent des trésors en main (sans l'Or maudit)."""
    return sum(money_value(card) * qty for card, qty in hand.items())
