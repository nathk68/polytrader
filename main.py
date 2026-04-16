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
from claude_analyst import log_prompts_for_manual_analysis, log_analysis_report
from trader import init_client, get_usdc_balance, check_and_close_positions

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

    logger.info(f"📋 {len(raw_opportunities)} opportunités détectées — génération des prompts")
    log_prompts_for_manual_analysis(raw_opportunities, max_prompts=5)


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
