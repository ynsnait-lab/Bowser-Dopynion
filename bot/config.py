"""Réglages du bot, modifiables par variables d'environnement (pratique sur Alwaysdata).

Une variable mal écrite ne doit jamais empêcher le bot de démarrer : on garde alors la
valeur par défaut (et /version montre la stratégie vraiment jouée).
"""

import os
from dataclasses import dataclass
from pathlib import Path


def _number(name: str, default: float) -> float:
    """Nombre lu dans une variable d'environnement, ou `default` s'il est absent ou illisible."""
    try:
        value = float(os.environ.get(name, default))
    except ValueError:
        return default
    return value if 0 <= value < 1e9 else default  # ni négatif, ni infini, ni « nan »


@dataclass
class Settings:
    # Nom renvoyé par /name (affiché sur le classement).
    team_name: str = os.environ.get("DOPYNION_TEAM_NAME", "Groupe 3")

    # "groupe3"    : la stratégie de l'équipe, un réglage par taille de table (par défaut).
    # "groupe3_v1" : la version du 12/10, gardée pour mesurer nos progrès.
    # "groupe3_v2" : la version du 13/10 (avant les règles des piles), idem.
    # "groupe3_v3" : la version du 20/10 (avant le re-réglage apparié du 26/10), idem.
    # "groupe3_v4" : la version du 26/10 (avant le calcul de risque en duel), idem.
    # "groupe3_v5" : la version du 26/10 au soir (avant la fin de partie jouée d'avance à 3 et 4), idem.
    # "groupe3_v6" : la version du 27/10 (avant l'égalité comptée pour un demi-duel en duel), idem.
    # "groupe3_v7" : la version du 27/10 au matin (avant les Sorcières du Royaume du 26/10), idem.
    # "groupe3_v8" : la version du 27/10 après-midi (avant la Milice et le Bandit du 27/10), idem.
    # "groupe3_v9" : la version du 27/10 au soir (avant le moteur 0.9.4 et la règle des égalités), idem.
    # "smithy_bm"  : Big Money + 2 Forgerons.
    # "big_money"  : trésors et cartes Victoire seulement (aussi la stratégie de relais).
    # "passive"    : on termine toujours le tour (connecté, zéro risque).
    # "koopa"      : copie de la stratégie actuelle de l'équipe (repo Bowser), pour comparer.
    # Plus les stratégies des bacs à sable (bot/strategy/essais_<prénom>.py).
    # Un nom inconnu (faute de frappe) : on joue "groupe3" plutôt que de ne rien faire.
    strategy: str = os.environ.get("DOPYNION_STRATEGY", "groupe3")

    # Dossier des journaux : un fichier JSONL par jour.
    log_dir: Path = Path(os.environ.get("DOPYNION_LOG_DIR", "logs"))
    # Ménage automatique des journaux (Alwaysdata gratuit : 1 Go pour tout le compte ; un bot
    # peut jouer ~3000 parties par jour à ~25 Ko chacune) : jours gardés, place maximale.
    log_days: int = int(_number("DOPYNION_LOG_DAYS", 7))
    log_max_mb: float = _number("DOPYNION_LOG_MAX_MB", 300)

    # Format des décisions de /play, confirmé par le client le 08/10 : "BUY <carte>" et "ACTION <carte>".
    buy_format: str = os.environ.get("DOPYNION_BUY_FORMAT", "BUY {card}")
    action_format: str = os.environ.get("DOPYNION_ACTION_FORMAT", "ACTION {card}")


settings = Settings()
