"""
Scanner — Récupère les marchés Polymarket et identifie les opportunités
Le scanner fait un pré-filtre léger, Claude fait la vraie analyse ensuite.
"""
import logging
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional
from config import (
    CLOB_HOST, GAMMA_HOST,
    EXPIRY_WINDOW_DAYS, MIN_VOLUME_24H,
    MIN_PROB, MAX_PROB
)

logger = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "PolyBot/1.0"})


def fetch_active_markets(limit: int = 200) -> list[dict]:
    try:
        url = f"{GAMMA_HOST}/markets"
        params = {
            "active": "true",
            "closed": "false",
            "limit": limit,
            "order": "volume24hr",
            "ascending": "false",
        }
        resp = SESSION.get(url, params=params, timeout=15)
        resp.raise_for_status()
        markets = resp.json()
        logger.info(f"✅ {len(markets)} marchés récupérés")
        return markets
    except Exception as e:
        logger.error(f"Erreur fetch marchés: {e}")
        return []


def fetch_orderbook(token_id: str) -> Optional[dict]:
    try:
        url = f"{CLOB_HOST}/book"
        params = {"token_id": token_id}
        resp = SESSION.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.debug(f"Orderbook error pour {token_id}: {e}")
        return None


def get_spread(orderbook: dict) -> float:
    try:
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])
        if not bids or not asks:
            return 1.0
        best_bid = float(bids[0]["price"])
        best_ask = float(asks[0]["price"])
        mid = (best_bid + best_ask) / 2
        spread = (best_ask - best_bid) / mid if mid > 0 else 1.0
        return round(spread, 4)
    except Exception:
        return 1.0


def days_until_expiry(end_date_str: str) -> Optional[float]:
    if not end_date_str:
        return None
    try:
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d"):
            try:
                end_dt = datetime.strptime(end_date_str, fmt).replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                delta = (end_dt - now).total_seconds() / 86400
                return round(delta, 2)
            except ValueError:
                continue
        return None
    except Exception:
        return None


def score_opportunity(volume_24h: float, days_left: float) -> float:
    """
    Score de pré-filtrage basé uniquement sur des critères objectifs.
    L'edge réel sera calculé par Claude — on ne l'estime pas ici.
    """
    score = 0.0

    # Urgence résolution
    if days_left <= 1:
        score += 40
    elif days_left <= 3:
        score += 30
    elif days_left <= 7:
        score += 15

    # Volume / liquidité
    if volume_24h >= 50000:
        score += 30
    elif volume_24h >= 10000:
        score += 20
    elif volume_24h >= 1000:
        score += 10

    return round(score, 2)


def scan_opportunities() -> list[dict]:
    """
    Pré-filtre : récupère les marchés intéressants à soumettre à Claude.
    On ne calcule PAS d'edge ici — c'est le job de Claude.
    On filtre uniquement sur : expiry, volume, liquidité, marché binaire.
    """
    markets = fetch_active_markets()
    opportunities = []

    for market in markets:
        if not market.get("active") or market.get("closed"):
            continue

        end_date = market.get("endDateIso") or market.get("endDate")
        days_left = days_until_expiry(end_date)

        if days_left is None or days_left < 0 or days_left > EXPIRY_WINDOW_DAYS:
            continue

        volume_24h = float(market.get("volume24hr", 0))
        if volume_24h < MIN_VOLUME_24H:
            continue

        tokens = market.get("tokens", [])
        if len(tokens) != 2:
            continue  # Marchés binaires YES/NO uniquement

        # On prend le token YES (le plus souvent l'outcome principal)
        for token in tokens:
            outcome = token.get("outcome", "")
            price = float(token.get("price", 0))

            # Filtre de zone : on veut des marchés avec une vraie incertitude
            # Zone 0.55-0.97 : assez probable mais pas "certain"
            # Zone 0.03-0.45 : l'outcome contraire est probable
            if not (0.55 <= price <= 0.97):
                continue

            token_id = token.get("token_id", "")
            orderbook = fetch_orderbook(token_id) if token_id else None
            spread = get_spread(orderbook) if orderbook else 0.05

            # Filtre spread
            if spread > 0.08:
                continue

            score = score_opportunity(volume_24h, days_left)

            opportunity = {
                "question":      market.get("question", ""),
                "market_id":     market.get("conditionId", ""),
                "token_id":      token_id,
                "outcome":       outcome,
                "price":         price,
                "prob_estimate": price,  # Placeholder — sera remplacé par Claude
                "edge":          0.0,    # Sera calculé par Claude
                "spread":        spread,
                "volume_24h":    volume_24h,
                "days_left":     days_left,
                "score":         score,
                "strategy":      _detect_strategy(days_left),
            }
            opportunities.append(opportunity)
            break  # Un seul token par marché pour le pré-filtre

    opportunities.sort(key=lambda x: x["score"], reverse=True)
    logger.info(f"🔍 {len(opportunities)} opportunités pré-filtrées pour Claude")
    return opportunities


def _detect_strategy(days_left: float) -> str:
    if days_left <= 3:
        return "EXPIRY_SNIPE"
    elif days_left <= 7:
        return "EXPIRY_APPROACH"
    else:
        return "STANDARD"
