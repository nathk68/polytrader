"""
Risk Management — Kelly Criterion + règles de protection du capital
"""
import logging
from config import (
    BANKROLL_USDC, MAX_POSITION_PCT, MIN_EDGE_THRESHOLD, MAX_SPREAD_PCT
)

logger = logging.getLogger(__name__)


def kelly_fraction(prob_estimate: float, market_price: float) -> float:
    if market_price <= 0 or market_price >= 1:
        return 0.0
    b = (1 / market_price) - 1
    p = prob_estimate
    q = 1 - p
    kelly = (b * p - q) / b
    if kelly <= 0:
        return 0.0
    return round(kelly / 2, 4)


def compute_position_size(
    prob_estimate: float,
    market_price: float,
    current_bankroll: float
) -> float:
    fraction = kelly_fraction(prob_estimate, market_price)
    if fraction <= 0:
        return 0.0
    raw_size = fraction * current_bankroll
    max_size = MAX_POSITION_PCT * current_bankroll
    position = round(min(raw_size, max_size), 2)
    logger.info(
        f"Position sizing: Kelly={fraction:.2%} | Raw={raw_size:.2f}$ | "
        f"Capped={position:.2f}$ | Bankroll={current_bankroll:.2f}$"
    )
    return position


def compute_edge(prob_estimate: float, market_price: float) -> float:
    return round(prob_estimate - market_price, 4)


def is_trade_valid(
    prob_estimate: float,
    market_price: float,
    spread_pct: float,
    volume_24h: float,
    min_volume: float
) -> tuple[bool, str]:
    edge = compute_edge(prob_estimate, market_price)
    if edge < MIN_EDGE_THRESHOLD:
        return False, f"Edge insuffisant: {edge:.2%} < {MIN_EDGE_THRESHOLD:.2%}"
    if spread_pct > MAX_SPREAD_PCT:
        return False, f"Spread trop large: {spread_pct:.2%} > {MAX_SPREAD_PCT:.2%}"
    if volume_24h < min_volume:
        return False, f"Volume insuffisant: ${volume_24h:.0f} < ${min_volume:.0f}"
    if market_price < 0.05:
        return False, f"Prix trop bas: {market_price}"
    if market_price > 0.98:
        return False, f"Prix trop proche de 1: {market_price}"
    return True, "OK"


def log_trade_summary(opportunity: dict, position_size: float):
    logger.info("=" * 55)
    logger.info(f"🎯 TRADE DÉTECTÉ")
    logger.info(f"   Marché   : {opportunity.get('question', 'N/A')[:60]}")
    logger.info(f"   Outcome  : {opportunity.get('outcome', 'N/A')}")
    logger.info(f"   Prix mkt : {opportunity.get('price', 0):.2%}")
    logger.info(f"   Notre est: {opportunity.get('prob_estimate', 0):.2%}")
    logger.info(f"   Edge     : {opportunity.get('edge', 0):.2%}")
    logger.info(f"   Position : {position_size:.2f} USDC")
    logger.info(f"   Stratégie: {opportunity.get('strategy', 'N/A')}")
    logger.info("=" * 55)
