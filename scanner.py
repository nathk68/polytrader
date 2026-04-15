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
            if isinstance(data, list):
                markets = data
            elif isinstance(data, dict):
                markets = data.get("data", data.get("markets", []))
            else:
                markets = []
            if markets:
                logger.info(f"✅ {len(markets)} marchés récupérés depuis {url}")
                return markets
        except Exception as e:
            logger.warning(f"Erreur fetch {url}: {e}")
            continue
    logger.error("❌ Impossible de récupérer les marchés")
    return []


def fetch_orderbook(token_id: str) -> Optional[dict]:
    try:
        resp = SESSION.get(f"{CLOB_HOST}/book", params={"token_id": token_id}, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
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

    # ── Stats de debug pour comprendre les filtres ──
    stats = {
        "total": len(markets),
        "inactive": 0,
        "no_expiry": 0,
        "expiry_too_far": 0,
        "low_volume": 0,
        "not_binary": 0,
        "price_out_of_range": 0,
        "spread_too_high": 0,
        "passed": 0,
    }

    # Aperçu des marchés pour calibrer les filtres
    expiries = []
    volumes = []
    for m in markets[:20]:
        end_date = m.get("endDateIso") or m.get("endDate") or m.get("resolutionTime")
        d = days_until_expiry(end_date)
        if d:
            expiries.append(d)
        v = float(m.get("volume24hr", m.get("volume", 0)))
        if v > 0:
            volumes.append(v)

    if expiries:
        logger.info(
            f"📅 Expiries (échantillon 20): "
            f"min={min(expiries):.0f}j | "
            f"median={sorted(expiries)[len(expiries)//2]:.0f}j | "
            f"max={max(expiries):.0f}j"
        )
    if volumes:
        logger.info(
            f"📊 Volumes 24h (échantillon 20): "
            f"min=${min(volumes):.0f} | "
            f"median=${sorted(volumes)[len(volumes)//2]:.0f} | "
            f"max=${max(volumes):.0f}"
        )

    opportunities = []

    for market in markets:
        active = market.get("active", market.get("isActive", True))
        closed = market.get("closed", market.get("isClosed", False))
        if not active or closed:
            stats["inactive"] += 1
            continue

        end_date = (
            market.get("endDateIso") or market.get("endDate")
            or market.get("end_date_iso") or market.get("resolutionTime")
        )
        days_left = days_until_expiry(end_date)

        if days_left is None or days_left < 0:
            stats["no_expiry"] += 1
            continue

        if days_left > EXPIRY_WINDOW_DAYS:
            stats["expiry_too_far"] += 1
            continue

        volume_24h = float(market.get("volume24hr", market.get("volume", 0)))
        if volume_24h < MIN_VOLUME_24H:
            stats["low_volume"] += 1
            continue

        tokens = market.get("tokens", market.get("outcomes", []))
        if len(tokens) != 2:
            stats["not_binary"] += 1
            continue

        added = False
        for token in tokens:
            outcome = token.get("outcome", token.get("title", ""))
            price = float(token.get("price", token.get("probability", 0)))

            if not (0.55 <= price <= 0.97):
                continue

            token_id = token.get("token_id", token.get("id", ""))
            orderbook = fetch_orderbook(token_id) if token_id else None
            spread = get_spread(orderbook) if orderbook else 0.03

            if spread > 0.08:
                stats["spread_too_high"] += 1
                continue

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
                "prob_estimate": price,
                "edge":          0.0,
                "spread":        spread,
                "volume_24h":    volume_24h,
                "days_left":     days_left,
                "score":         score,
                "strategy":      "EXPIRY_SNIPE" if days_left <= 3 else "EXPIRY_APPROACH",
            })
            stats["passed"] += 1
            added = True
            break

        if not added:
            stats["price_out_of_range"] += 1

    logger.info(
        f"🔍 Filtres: total={stats['total']} | "
        f"inactif={stats['inactive']} | "
        f"trop_loin={stats['expiry_too_far']} | "
        f"faible_vol={stats['low_volume']} | "
        f"prix_hors_range={stats['price_out_of_range']} | "
        f"✅ passés={stats['passed']}"
    )

    opportunities.sort(key=lambda x: x["score"], reverse=True)
    logger.info(f"🎯 {len(opportunities)} opportunités envoyées à Claude")
    return opportunities
