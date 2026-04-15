"""
PolyBot v2 — Polymarket Trading Bot + Claude AI Analyst
Usage:
    python main.py              → DRY RUN (simulation)
    DRY_RUN=false python main.py → LIVE (vrais ordres)
"""
import os
import time
import logging
import schedule
from datetime import datetime, timezone

from config import SCAN_INTERVAL_MINUTES, MIN_VOLUME_24H, BANKROLL_USDC
from scanner import scan_opportunities
from claude_analyst import batch_analyze, log_analysis_report
from risk import compute_position_size, is_trade_valid, log_trade_summary
from trader import init_client, get_usdc_balance, execute_opportunity, check_and_close_positions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("polybot.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("PolyBot")

DRY_RUN = os.getenv("DRY_RUN", "true").lower() != "false"


class BotState:
    def __init__(self):
        self.bankroll = BANKROLL_USDC
        self.trades_today = 0
        self.max_trades_per_day = 5
        self.positions_taken = set()
        self.total_pnl = 0.0
        self.session_start = datetime.now(timezone.utc)
        self.claude_analyses_today = 0
        self.max_claude_analyses = 20

    def can_trade(self) -> bool:
        if self.bankroll < 2.0:
            logger.warning("⚠️  Balance trop faible (<2$)")
            return False
        if self.trades_today >= self.max_trades_per_day:
            logger.info(f"📊 Limite journalière atteinte ({self.max_trades_per_day} trades)")
            return False
        return True

    def can_analyze(self) -> bool:
        return self.claude_analyses_today < self.max_claude_analyses

    def reset_daily(self):
        self.trades_today = 0
        self.claude_analyses_today = 0
        logger.info("🔄 Compteurs journaliers réinitialisés")

    def summary(self) -> str:
        uptime = datetime.now(timezone.utc) - self.session_start
        return (
            f"\n{'='*60}\n"
            f"  🤖 PolyBot v2 — Session Summary\n"
            f"  Uptime          : {str(uptime).split('.')[0]}\n"
            f"  Bankroll        : {self.bankroll:.2f}$ (départ: {BANKROLL_USDC}$)\n"
            f"  PnL session     : {self.total_pnl:+.2f}$\n"
            f"  Trades today    : {self.trades_today}/{self.max_trades_per_day}\n"
            f"  Analyses Claude : {self.claude_analyses_today}/{self.max_claude_analyses}\n"
            f"  Mode            : {'🟡 DRY RUN' if DRY_RUN else '🟢 LIVE'}\n"
            f"{'='*60}"
        )


def run_trading_cycle(client, state: BotState):
    logger.info(f"\n{'─'*50}")
    logger.info(f"⏱️  Cycle | {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC")
    logger.info(f"{'─'*50}")

    check_and_close_positions(client, dry_run=DRY_RUN)

    if not DRY_RUN:
        state.bankroll = get_usdc_balance(client)

    if not state.can_trade():
        return

    raw_opportunities = scan_opportunities()

    if not raw_opportunities:
        logger.info("😴 Aucune opportunité pré-filtrée ce cycle")
        return

    logger.info(f"📡 {len(raw_opportunities)} opportunités → envoi à Claude")

    if not state.can_analyze():
        logger.warning("⚠️  Limite analyses Claude atteinte aujourd'hui")
        return

    max_to_analyze = min(5, state.max_claude_analyses - state.claude_analyses_today)
    validated_opportunities = batch_analyze(opportunities=raw_opportunities, max_analyses=max_to_analyze)
    state.claude_analyses_today += min(len(raw_opportunities), max_to_analyze)

    log_analysis_report(validated_opportunities)

    if not validated_opportunities:
        logger.info("🧠 Claude n'a validé aucun trade ce cycle.")
        return

    executed = 0

    for opp in validated_opportunities:
        if not state.can_trade() or executed >= 2:
            break

        token_id = opp.get("token_id", "")
        if token_id in state.positions_taken:
            continue

        valid, reason = is_trade_valid(
            prob_estimate=opp["prob_estimate"],
            market_price=opp["price"],
            spread_pct=opp["spread"],
            volume_24h=opp["volume_24h"],
            min_volume=MIN_VOLUME_24H,
        )

        if not valid:
            logger.info(f"  ❌ Risk check: {reason}")
            continue

        confidence = opp.get("claude_confidence", "low")
        if confidence == "low":
            logger.info(f"  ⏭️  Skip: confiance Claude faible")
            continue

        position_size = compute_position_size(
            prob_estimate=opp["prob_estimate"],
            market_price=opp["price"],
            current_bankroll=state.bankroll,
        )

        if position_size < 1.0:
            continue

        log_trade_summary(opp, position_size)
        success = execute_opportunity(client, opp, position_size, dry_run=DRY_RUN)

        if success:
            state.trades_today += 1
            state.bankroll -= position_size
            state.positions_taken.add(token_id)
            executed += 1
            logger.info(
                f"  ✅ Trade #{state.trades_today} | "
                f"Balance: {state.bankroll:.2f}$ | "
                f"Confiance Claude: {confidence.upper()}"
            )

    if executed == 0:
        logger.info("💤 Aucun trade exécuté ce cycle")


def main():
    logger.info("=" * 60)
    logger.info("  🤖 PolyBot v2 — Claude AI + Polymarket")
    logger.info(f"  Mode    : {'🟡 DRY RUN' if DRY_RUN else '🟢 LIVE TRADING'}")
    logger.info(f"  Capital : {BANKROLL_USDC}$")
    logger.info(f"  Scan    : toutes les {SCAN_INTERVAL_MINUTES} minutes")
    logger.info("=" * 60)

    if DRY_RUN:
        logger.warning("⚠️  DRY RUN actif — aucun ordre réel.\n")

    try:
        client = init_client()
    except Exception as e:
        logger.critical(f"Impossible d'initialiser le client CLOB: {e}")
        return

    state = BotState()

    schedule.every().day.at("00:00").do(state.reset_daily)
    schedule.every(SCAN_INTERVAL_MINUTES).minutes.do(run_trading_cycle, client=client, state=state)
    schedule.every().hour.do(lambda: logger.info(state.summary()))

    run_trading_cycle(client, state)

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("\n🛑 Bot arrêté")
        logger.info(state.summary())


if __name__ == "__main__":
    main()
