"""
Scanner — Récupère les marchés Polymarket et identifie les opportunités
"""
import logging
import requests
from datetime import datetime, timezone
from typing import Optional
from config import (
    CLOB_HOST, GAMMA_HOST,
    EXPIRY_WINDOW_DAYS, MIN_VOLUME_24H,
)

logger = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "PolyBot/1.0"})


def fetch_active_markets(limit: int = 200) -> list[dict]:
    # Essaie d'abord l'API Gamma, puis fallback sur le CLOB
    endpoints = [
        f"{GAMMA_HOST}/markets",
        f"{CLOB_HOST}/markets",
    ]
    params = {
        "active": "true",
        "closed": "false",
        "limit": limit,
        "order": "volume24hr",
        "ascending": "false",
    }
    for url in endpoints:
        try:
            resp = SESSION.get(url, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()

            # L'API peut retourner une liste ou un objet {data: [...]}
            if isinstance(data, list):
                markets = data
            elif isinstance(data, dict):
                markets = data.get("data", data.get("markets", []))
            else:
                markets = []

            if markets:
                logger.info(f"✅ {len(markets)} marchés récupérés depuis {url}")
                return markets
            else:
                logger.warning(f"Réponse vide depuis {url}, essai suivant...")

        except Exception as e:
            logger.warning(f"Erreur fetch {url}: {e}")
            continue

    logger.error("❌ Impossible de récupérer les marchés (toutes les sources ont échoué)")
    return []


def fetch_orderbook(token_id: str) -> Optional[dict]:
    try:
        url = f"{CLOB_HOST}/book"
        resp = SESSION.get(url, params={"token_id": token_id}, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.debug(f"Orderbook error {token_id[:20]}: {e}")
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
        return round((best_ask - best_bid) / mid, 4) if mid > 0 else 1.0
    except Exception:
        return 1.0


def days_until_expiry(end_date_str: str) -> Optional[float]:
    if not end_date_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d"):
        try:
            end_dt = datetime.strptime(end_date_str, fmt).replace(tzinfo=timezone.utc)
            delta = (end_dt - datetime.now(timezone.utc)).total_seconds() / 86400
            return round(delta, 2)
        except ValueError:
            continue
    return None


def scan_opportunities() -> list[dict]:
    markets = fetch_active_markets()

    if not markets:
        return []

    opportunities = []

    for market in markets:
        # Filtre actif/fermé — gère les deux formats possibles de l'API
        active = market.get("active", market.get("isActive", True))
        closed = market.get("closed", market.get("isClosed", False))
        if not active or closed:
            continue

        # Date d'expiration
        end_date = (
            market.get("endDateIso")
            or market.get("endDate")
            or market.get("end_date_iso")
            or market.get("resolutionTime")
        )
        days_left = days_until_expiry(end_date)
        if days_left is None or days_left < 0 or days_left > EXPIRY_WINDOW_DAYS:
            continue

        # Volume
        volume_24h = float(
            market.get("volume24hr", market.get("volume", 0))
        )
        if volume_24h < MIN_VOLUME_24H:
            continue

        # Tokens / outcomes
        tokens = market.get("tokens", market.get("outcomes", []))
        if len(tokens) != 2:
            continue

        for token in tokens:
            outcome = token.get("outcome", token.get("title", ""))
            price = float(token.get("price", token.get("probability", 0)))

            if not (0.55 <= price <= 0.97):
                continue

            token_id = token.get("token_id", token.get("id", ""))
            orderbook = fetch_orderbook(token_id) if token_id else None
            spread = get_spread(orderbook) if orderbook else 0.03

            if spread > 0.08:
                continue

            # Score basé sur urgence + liquidité uniquement
            score = 0.0
            if days_left <= 1:   score += 40
            elif days_left <= 3: score += 30
            elif days_left <= 7: score += 15
            if volume_24h >= 50000:   score += 30
            elif volume_24h >= 10000: score += 20
            elif volume_24h >= 1000:  score += 10

            opportunities.append({
                "question":      market.get("question", market.get("title", "")),
                "market_id":     market.get("conditionId", market.get("id", "")),
                "token_id":      token_id,
                "outcome":       outcome,
                "price":         price,
                "prob_estimate": price,   # Sera remplacé par Claude
                "edge":          0.0,     # Sera calculé par Claude
                "spread":        spread,
                "volume_24h":    volume_24h,
                "days_left":     days_left,
                "score":         score,
                "strategy":      "EXPIRY_SNIPE" if days_left <= 3 else "EXPIRY_APPROACH",
            })
            break  # Un token par marché suffit pour le pré-filtre

    opportunities.sort(key=lambda x: x["score"], reverse=True)
    logger.info(f"🔍 {len(opportunities)} opportunités pré-filtrées pour Claude")
    return opportunities
