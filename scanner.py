"""
Scanner — Récupère les marchés Polymarket et identifie les opportunités
"""
import logging
import requests
from datetime import datetime, timezone
from typing import Optional
from config import CLOB_HOST, GAMMA_HOST, EXPIRY_WINDOW_DAYS, MIN_VOLUME_24H

logger = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "PolyBot/1.0"})


def fetch_active_markets(limit: int = 200) -> list[dict]:
    endpoints = [f"{GAMMA_HOST}/markets", f"{CLOB_HOST}/markets"]
    params = {"active": "true", "closed": "false", "limit": limit, "order": "volume24hr", "ascending": "false"}
    for url in endpoints:
        try:
            resp = SESSION.get(url, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            markets = data if isinstance(data, list) else data.get("data", data.get("markets", []))
            if markets:
                logger.info(f"✅ {len(markets)} marchés récupérés")
                return markets
        except Exception as e:
            logger.warning(f"Erreur fetch {url}: {e}")
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
            return round((end_dt - datetime.now(timezone.utc)).total_seconds() / 86400, 2)
        except ValueError:
            continue
    return None


def scan_opportunities() -> list[dict]:
    markets = fetch_active_markets()
    if not markets:
        return []

    stats = {"total": len(markets), "inactive": 0, "no_expiry": 0, "trop_loin": 0,
             "low_volume": 0, "no_tokens": 0, "prix_hors_range": 0, "spread_trop_haut": 0, "passed": 0}

    # Debug : aperçu expiries et volumes
    expiries = []
    for m in markets[:30]:
        end = m.get("endDateIso") or m.get("endDate") or m.get("resolutionTime")
        d = days_until_expiry(end)
        if d and d > 0:
            expiries.append(d)
    if expiries:
        s = sorted(expiries)
        logger.info(f"📅 Expiries échantillon: min={s[0]:.0f}j | median={s[len(s)//2]:.0f}j | max={s[-1]:.0f}j")

    opportunities = []

    for market in markets:
        active = market.get("active", market.get("isActive", True))
        closed = market.get("closed", market.get("isClosed", False))
        if not active or closed:
            stats["inactive"] += 1
            continue

        end_date = (market.get("endDateIso") or market.get("endDate")
                    or market.get("end_date_iso") or market.get("resolutionTime"))
        days_left = days_until_expiry(end_date)

        if days_left is None or days_left < 0:
            stats["no_expiry"] += 1
            continue
        if days_left > EXPIRY_WINDOW_DAYS:
            stats["trop_loin"] += 1
            continue

        volume_24h = float(market.get("volume24hr", market.get("volume", 0)))
        if volume_24h < MIN_VOLUME_24H:
            stats["low_volume"] += 1
            continue

        # Accepte tous les marchés avec au moins 2 outcomes (pas uniquement binaires)
        tokens_raw = market.get("tokens", [])
        if not tokens_raw:
            # Gamma API: outcomes peut être une liste de strings ou une string JSON
            outcomes_raw = market.get("outcomes", [])
            if isinstance(outcomes_raw, str):
                import json as _json
                try:
                    outcomes_raw = _json.loads(outcomes_raw)
                except Exception:
                    outcomes_raw = []
            prices_raw = market.get("outcomePrices", [])
            if isinstance(prices_raw, str):
                import json as _json
                try:
                    prices_raw = _json.loads(prices_raw)
                except Exception:
                    prices_raw = []
            tokens_raw = [
                {
                    "outcome": str(o),
                    "price": float(prices_raw[i]) if i < len(prices_raw) else 0.0,
                    "token_id": "",
                }
                for i, o in enumerate(outcomes_raw)
            ]
        # Normalise au cas où certains tokens seraient déjà des strings
        tokens = []
        for t in tokens_raw:
            if isinstance(t, str):
                tokens.append({"outcome": t, "price": 0.0, "token_id": ""})
            else:
                tokens.append(t)

        if len(tokens) < 2:
            stats["no_tokens"] += 1
            continue

        added = False
        for token in tokens:
            outcome = token.get("outcome", token.get("title", ""))
            price = float(token.get("price", token.get("probability", 0)))

            # Zone cible : outcomes assez probables mais pas certains
            if not (0.55 <= price <= 0.97):
                continue

            token_id = token.get("token_id", token.get("id", ""))
            orderbook = fetch_orderbook(token_id) if token_id else None
            spread = get_spread(orderbook) if orderbook else 0.03

            if spread > 0.10:   # Un peu plus permissif
                stats["spread_trop_haut"] += 1
                continue

            score = 0.0
            if days_left <= 1:   score += 40
            elif days_left <= 3: score += 30
            elif days_left <= 7: score += 20
            elif days_left <= 14: score += 10
            if volume_24h >= 50000:   score += 30
            elif volume_24h >= 10000: score += 20
            elif volume_24h >= 1000:  score += 10
            elif volume_24h >= 500:   score += 5

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
            break  # Un token par marché pour le pré-filtre

        if not added and stats["spread_trop_haut"] == 0:
            stats["prix_hors_range"] += 1

    logger.info(
        f"🔍 Filtres: total={stats['total']} | inactif={stats['inactive']} | "
        f"trop_loin={stats['trop_loin']} | low_vol={stats['low_volume']} | "
        f"no_tokens={stats['no_tokens']} | prix_hors_range={stats['prix_hors_range']} | "
        f"spread_haut={stats['spread_trop_haut']} | ✅ passés={stats['passed']}"
    )
    opportunities.sort(key=lambda x: x["score"], reverse=True)
    return opportunities
