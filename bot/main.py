"""API HTTP du bot Dopynion du groupe 3.

Règle d'or : une réponse invalide = disqualification. Donc chaque route :
1. lit la requête sans jamais planter (corps illisible = corps vide) ;
2. demande une décision à la stratégie (bot/strategy/, bot/safety.py) ;
3. vérifie que la décision est autorisée (carte présente dans la liste reçue ; pour /play,
   les règles du moteur : main, actions, achats, argent, réserve) ;
4. sinon, ou si quelque chose plante, demande à une stratégie de relais très simple
   (Big Money), vérifiée de la même façon, puis en dernier recours une réponse de secours sûre ;
5. journalise l'échange (bot/journal.py).

Une stratégie qui plante ne coûte donc qu'un coup moins bon, jamais la partie.
"""

import html
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from bot import safety
from bot.config import settings
from bot.journal import log_exchange
from bot.memory import memories
from bot.strategy import END_TURN, STRATEGIES, decide_play, read_state

DEFAULT_STRATEGY = "groupe3"  # si DOPYNION_STRATEGY ne correspond à aucune stratégie
BACKUP_STRATEGY = "big_money"  # relais si la stratégie plante ou propose un coup interdit
REPO = Path(__file__).resolve().parent.parent


class IllegalDecisionError(Exception):
    """Coup contraire aux règles du moteur : l'arbitre éliminerait le royaume."""


def active_strategy() -> str:
    """La stratégie demandée, ou la stratégie de l'équipe si ce nom n'existe pas (faute de frappe)."""
    return settings.strategy if settings.strategy in STRATEGIES else DEFAULT_STRATEGY


def code_version(root: Path = REPO) -> str:
    """Le commit déployé, lu dans .git sans lancer git (« inconnue » hors d'un dépôt git)."""
    try:
        git = root / ".git"
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            ref = head.removeprefix("ref: ")
            if (git / ref).exists():
                head = (git / ref).read_text(encoding="utf-8").strip()
            else:  # références rangées dans packed-refs (git gc)
                packed = (git / "packed-refs").read_text(encoding="utf-8").splitlines()
                head = next(line.split()[0] for line in packed if line.endswith(f" {ref}"))
        return head[:7]
    except Exception:  # noqa: BLE001 - un numéro de version ne doit jamais empêcher de démarrer
        return "inconnue"


VERSION = code_version()
if settings.strategy not in STRATEGIES:
    print(f"[config] stratégie {settings.strategy!r} inconnue : on joue {DEFAULT_STRATEGY!r}", file=sys.stderr)

app = FastAPI(title="Bot Dopynion du groupe 3")

GameIdHeader = Annotated[str, Header(description="Identifiant de la partie, renvoyé tel quel")]


#####################################################
# Format des réponses (même JSON que le template)
#####################################################


class DopynionResponseBool(BaseModel):
    game_id: str
    decision: bool


class DopynionResponseStr(BaseModel):
    game_id: str
    decision: str


class DopynionResponseCardName(DopynionResponseStr):
    """Le nom de carte reste du texte : on ne le revalide pas contre notre
    version du moteur, qui pourrait ignorer une carte récente de l'arbitre."""


#####################################################
# Outils communs : lire, décider, vérifier, journaliser
#####################################################


async def read_body(request: Request) -> Any:
    """Corps JSON de la requête, ou {} s'il est vide ou illisible."""
    try:
        raw = await request.body()
        return json.loads(raw) if raw else {}
    except Exception:  # noqa: BLE001
        return {}


def card_list(received: Any, key: str) -> list[str]:
    """Liste de cartes reçue (main, cartes possibles...), sans ce qui n'est pas du texte."""
    values = received.get(key) if isinstance(received, dict) else None
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str)]


def decide(
    route: str,
    game_id: str,
    received: Any,
    propose: Callable[[], Any],
    is_valid: Callable[[Any], bool],
    fallback: Any,
    backup: Callable[[], Any] | None = None,
) -> Any:
    """Décision de la stratégie si elle est valide, sinon celle du relais (`backup`),
    sinon la réponse de secours (toujours valide)."""
    start = time.perf_counter()
    errors: list[str] = []
    decision = fallback
    for attempt in (propose, backup):
        if attempt is None:
            continue
        try:
            proposal = attempt()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")
            continue
        if is_valid(proposal):
            decision = proposal
            break
        errors.append(f"décision refusée : {proposal!r}")
    log_exchange(
        route=route,
        game_id=game_id,
        received=received,
        decision=decision,
        duration_ms=(time.perf_counter() - start) * 1000,
        error=" ; ".join(errors) or None,
    )
    return decision


def card_decision(
    route: str,
    game_id: str,
    received: Any,
    key: str,
    choose: Callable[[list[str]], str],
) -> DopynionResponseCardName:
    options = card_list(received, key)
    decision = decide(
        route,
        game_id,
        received,
        propose=lambda: choose(options),
        is_valid=lambda card: card in options,
        fallback=options[0] if options else "NONE",
    )
    return DopynionResponseCardName(game_id=game_id, decision=decision)


def bool_decision(
    route: str,
    game_id: str,
    received: Any,
    choose: Callable[[], bool],
) -> DopynionResponseBool:
    decision = decide(
        route,
        game_id,
        received,
        propose=choose,
        is_valid=lambda value: isinstance(value, bool),
        fallback=False,
    )
    return DopynionResponseBool(game_id=game_id, decision=decision)


def lifecycle_decision(route: str, game_id: str, action: Callable[[], None]) -> DopynionResponseStr:
    def propose() -> str:
        action()
        return "OK"

    decision = decide(route, game_id, None, propose, lambda d: d == "OK", "OK")
    return DopynionResponseStr(game_id=game_id, decision=decision)


@app.exception_handler(Exception)
async def last_resort(request: Request, exc: Exception) -> JSONResponse:
    """Filet de sécurité ultime (normalement jamais atteint)."""
    log_exchange(
        route=request.url.path.strip("/"),
        game_id=request.headers.get("x-game-id", ""),
        received=None,
        decision=None,
        duration_ms=0,
        error=f"{type(exc).__name__}: {exc}",
    )
    return JSONResponse(
        status_code=500,
        content={"message": "Oops!", "detail": str(exc), "name": type(exc).__name__},
    )


#####################################################
# Cycle de vie et identité
#####################################################


@app.get("/", response_class=HTMLResponse)
def root() -> str:
    # Contrairement au template, on n'affiche PAS notre code source :
    # les autres équipes pourraient copier notre stratégie.
    team = html.escape(settings.team_name)
    return (
        f"<html><head><title>{team}</title></head><body>"
        f"<h1>{team}</h1><p>Bot Dopynion en ligne.</p>"
        '<p><a href="/docs">Documentation de l\'API</a></p>'
        "</body></html>"
    )


@app.get("/name")
def name() -> str:
    return settings.team_name


@app.get("/version")
def version() -> dict[str, str]:
    """Le commit en ligne et la stratégie jouée : pour savoir quel code tourne sur quel bot.
    L'arbitre ne l'appelle pas."""
    return {"version": VERSION, "strategie": active_strategy()}


@app.get("/start_game")
def start_game(x_game_id: GameIdHeader = "") -> DopynionResponseStr:
    return lifecycle_decision("start_game", x_game_id, lambda: memories.get(x_game_id))


@app.get("/start_turn")
def start_turn(x_game_id: GameIdHeader = "") -> DopynionResponseStr:
    return lifecycle_decision("start_turn", x_game_id, lambda: memories.get(x_game_id).new_turn())


@app.get("/end_game")
def end_game(x_game_id: GameIdHeader = "") -> DopynionResponseStr:
    return lifecycle_decision("end_game", x_game_id, lambda: memories.forget(x_game_id))


#####################################################
# Le tour de jeu
#####################################################


@app.post("/play")
async def play(request: Request, x_game_id: GameIdHeader = "") -> DopynionResponseStr:
    state = await read_body(request)

    def attempt(strategy: str) -> Callable[[], str]:
        def propose() -> str:
            memory = memories.get(x_game_id)
            hand, stock = read_state(state, settings.team_name)
            decision = decide_play(state, memory, strategy, settings.team_name)
            if not safety.legal_play(decision, hand, stock, memory):
                raise IllegalDecisionError(f"{strategy} propose « {decision.as_text()} », interdit ici")
            text = decision.as_text()
            memory.record(decision, hand)
            return text

        return propose

    decision = decide(
        "play",
        x_game_id,
        state,
        attempt(active_strategy()),
        is_valid=lambda d: isinstance(d, str) and d != "",
        fallback=END_TURN,
        backup=attempt(BACKUP_STRATEGY),
    )
    return DopynionResponseStr(game_id=x_game_id, decision=decision)


#####################################################
# Décisions demandées pendant un effet de carte
#####################################################


@app.post("/discard_card_from_hand")
async def discard_card_from_hand(
    request: Request,
    x_game_id: GameIdHeader = "",
) -> DopynionResponseCardName:
    received = await read_body(request)
    return card_decision("discard_card_from_hand", x_game_id, received, "hand", safety.choose_discard)


@app.post("/trash_card_from_hand")
async def trash_card_from_hand(
    request: Request,
    x_game_id: GameIdHeader = "",
) -> DopynionResponseCardName:
    received = await read_body(request)
    return card_decision("trash_card_from_hand", x_game_id, received, "hand", safety.choose_trash)


def gain_for(game_id: str) -> Callable[[list[str]], str]:
    """Choix d'une carte reçue (Atelier, Festin...) avec ce qu'on sait de la partie, carte notée dans
    notre mémoire : sinon on la prendrait pour l'achat d'un adversaire."""

    def choose(options: list[str]) -> str:
        memory = memories.get(game_id)
        card = safety.choose_gain(options, memory)
        memory.record_gain(card)
        return card

    return choose


@app.post("/choose_card_to_receive_in_discard")
async def choose_card_to_receive_in_discard(
    request: Request,
    x_game_id: GameIdHeader = "",
) -> DopynionResponseCardName:
    received = await read_body(request)
    return card_decision(
        "choose_card_to_receive_in_discard", x_game_id, received, "possible_cards", gain_for(x_game_id)
    )


@app.post("/choose_card_to_receive_in_deck")
async def choose_card_to_receive_in_deck(
    request: Request,
    x_game_id: GameIdHeader = "",
) -> DopynionResponseCardName:
    received = await read_body(request)
    return card_decision("choose_card_to_receive_in_deck", x_game_id, received, "possible_cards", gain_for(x_game_id))


@app.post("/trash_money_card_for_better_money_card")
async def trash_money_card_for_better_money_card(
    request: Request,
    x_game_id: GameIdHeader = "",
) -> DopynionResponseCardName:
    received = await read_body(request)
    return card_decision(
        "trash_money_card_for_better_money_card",
        x_game_id,
        received,
        "money_in_hand",
        safety.choose_mine,
    )


@app.post("/confirm_discard_card_from_hand")
async def confirm_discard_card_from_hand(
    request: Request,
    x_game_id: GameIdHeader = "",
) -> DopynionResponseBool:
    received = await read_body(request)
    return bool_decision(
        "confirm_discard_card_from_hand",
        x_game_id,
        received,
        lambda: safety.confirm_discard(received["card_name"], card_list(received, "hand")),
    )


@app.post("/confirm_trash_card_from_hand")
async def confirm_trash_card_from_hand(
    request: Request,
    x_game_id: GameIdHeader = "",
) -> DopynionResponseBool:
    received = await read_body(request)
    return bool_decision(
        "confirm_trash_card_from_hand",
        x_game_id,
        received,
        lambda: safety.confirm_trash(received["card_name"], card_list(received, "hand")),
    )


@app.post("/skip_card_reception_in_hand")
async def skip_card_reception_in_hand(
    request: Request,
    x_game_id: GameIdHeader = "",
) -> DopynionResponseBool:
    received = await read_body(request)
    return bool_decision(
        "skip_card_reception_in_hand",
        x_game_id,
        received,
        lambda: safety.skip_card_reception(received["card_name"], card_list(received, "hand")),
    )


@app.post("/confirm_discard_deck")
async def confirm_discard_deck(
    request: Request,
    x_game_id: GameIdHeader = "",
) -> DopynionResponseBool:
    received = await read_body(request)
    return bool_decision("confirm_discard_deck", x_game_id, received, safety.confirm_discard_deck)
