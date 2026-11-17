"""Collecte de données : chaque échange avec l'arbitre devient une ligne JSON.

Fichier : logs/AAAA-MM-JJ.jsonl (date UTC), une ligne par appel de l'arbitre.
Exploitable avec `python -m outils.analyse_logs` ou pandas.read_json(..., lines=True).

Le disque ne doit jamais se remplir (Alwaysdata gratuit : 1 Go pour tout le compte, et
l'arbitre peut faire jouer ~3000 parties par jour à un bot, ~25 Ko chacune) :
- les journaux de plus de DOPYNION_LOG_DAYS jours (7 par défaut) sont supprimés ;
- au-delà de DOPYNION_LOG_MAX_MB Mo (300 par défaut), les jours les plus anciens partent
  d'abord ; si le jour en cours dépasse à lui seul le plafond, on n'écrit plus que les
  échanges en erreur (jusqu'à 10 % au-dessus du plafond), puis plus rien.
Un souci de journal ne coûte jamais la partie : toutes ses erreurs sont avalées.
"""

import json
import sys
import threading
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from bot.config import settings

MB = 1024 * 1024
ERRORS_MARGIN = 1.1  # les erreurs ont droit à 10 % de place en plus : ce sont les lignes utiles

_lock = threading.Lock()
_cleaned: tuple[Path, date] | None = None  # dernier ménage (dossier, jour) : 1 fois par jour UTC
_older_bytes = 0  # taille des journaux des jours précédents, mesurée au dernier ménage
skipped = 0  # lignes non écrites faute de place, depuis le démarrage


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _path(day: date) -> Path:
    return settings.log_dir / f"{day:%Y-%m-%d}.jsonl"


def _day(path: Path) -> date | None:
    try:
        return date.fromisoformat(path.stem)
    except ValueError:
        return None


def clean(today: date, needed: int = 0) -> None:
    """Supprime les journaux trop vieux, puis les plus anciens tant que le total (plus `needed`
    octets à écrire) dépasse le plafond. Le journal du jour n'est jamais supprimé."""
    global _cleaned, _older_bytes
    older = []
    for path in sorted(settings.log_dir.glob("*.jsonl")):  # AAAA-MM-JJ : du plus ancien au plus récent
        day = _day(path)
        if day is None or day >= today:
            continue
        if (today - day).days >= settings.log_days:
            path.unlink(missing_ok=True)
        else:
            older.append(path)
    sizes = [_size(path) for path in older]
    while older and sum(sizes) + _size(_path(today)) + needed > settings.log_max_mb * MB:
        older.pop(0).unlink(missing_ok=True)
        sizes.pop(0)
    _cleaned, _older_bytes = (settings.log_dir, today), sum(sizes)


def _write(line: str, today: date, important: bool) -> None:
    """Ajoute la ligne au journal du jour s'il reste de la place (à appeler sous le verrou)."""
    global skipped
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    if _cleaned != (settings.log_dir, today):
        clean(today)
    path, budget, needed = _path(today), settings.log_max_mb * MB, len(line.encode())
    used = _older_bytes + _size(path) + needed
    if used > budget and _older_bytes:
        clean(today, needed)  # de la place en supprimant des jours précédents
        used = _older_bytes + _size(path) + needed
    if used > budget * (ERRORS_MARGIN if important else 1):
        skipped += 1
        return
    with path.open("a", encoding="utf-8") as file:
        file.write(line)


def log_exchange(
    *,
    route: str,
    game_id: str,
    received: Any,
    decision: Any,
    duration_ms: float,
    error: str | None = None,
) -> None:
    now = datetime.now(UTC)
    entry = {
        "ts": now.isoformat(timespec="milliseconds"),
        "game_id": game_id,
        "route": route,
        "received": received,
        "decision": decision,
        "duration_ms": round(duration_ms, 2),
        "fallback": error is not None,  # True = la réponse de secours (ou de relais) a été utilisée
    }
    if error:
        entry["error"] = error
    try:
        line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
        with _lock:
            _write(line, now.date(), important=error is not None)
    except Exception as exc:  # noqa: BLE001 - un souci de log ne doit jamais coûter la partie
        print(f"[journal] écriture impossible : {exc!r}", file=sys.stderr)
    if error:
        print(f"[secours] {route} ({game_id}) : {error}", file=sys.stderr)


def status() -> dict[str, Any]:
    """Où en sont les journaux (nombre de fichiers, place prise)."""
    try:
        files = list(settings.log_dir.glob("*.jsonl"))
        total = sum(_size(path) for path in files)
    except OSError:
        files, total = [], 0
    return {
        "fichiers": len(files),
        "taille_mo": round(total / MB, 1),
        "plafond_mo": settings.log_max_mb,
        "jours_gardes": settings.log_days,
        "lignes_non_ecrites": skipped,
    }
