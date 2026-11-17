"""Briques communes à toutes les stratégies : la décision envoyée à l'arbitre et le registre."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bot.config import settings

if TYPE_CHECKING:
    from bot.strategy.view import View

END_TURN = "END_TURN"


@dataclass(frozen=True)
class Decision:
    kind: str  # "END_TURN", "BUY" ou "ACTION"
    card: str | None = None

    def as_text(self) -> str:
        """Texte envoyé à l'arbitre."""
        if self.kind == "BUY":
            return settings.buy_format.format(card=self.card)
        if self.kind == "ACTION":
            return settings.action_format.format(card=self.card)
        return END_TURN


# Une stratégie reçoit ce que le bot sait (View) et renvoie une décision.
Strategy = Callable[["View"], Decision]

# Toutes les stratégies connues, par nom : utilisables par le bot (DOPYNION_STRATEGY),
# le simulateur et l'arbitre local.
STRATEGIES: dict[str, Strategy] = {}


def register(name: str, strategy: Strategy) -> Strategy:
    """Ajoute une stratégie au registre.

    Un nom déjà pris est refusé : un bac à sable ne peut pas remplacer par erreur
    la stratégie officielle (le bac à sable fautif est alors ignoré, avec un message).
    """
    if name in STRATEGIES:
        raise ValueError(f"le nom de stratégie {name!r} est déjà pris")
    STRATEGIES[name] = strategy
    return strategy


def passive(_view: "View") -> Decision:
    """On finit toujours le tour : connecté, zéro risque."""
    return Decision(END_TURN)


register("passive", passive)
