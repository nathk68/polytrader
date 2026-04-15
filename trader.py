"""
Trader — Connexion au CLOB Polymarket et exécution des ordres
"""
import logging
from typing import Optional
from config import CLOB_HOST, PRIVATE_KEY, POLYGON_RPC

logger = logging.getLogger(__name__)

_client = None


def init_client():
    global _client
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.constants import POLYGON

        if not PRIVATE_KEY:
            raise ValueError("PRIVATE_KEY manquante dans .env")

        client = ClobClient(
            host=CLOB_HOST,
            key=PRIVATE_KEY,
            chain_id=POLYGON,
        )

        # Dérivation clé API L2
        api_creds = client.create_or_derive_api_creds()
        client.set_api_creds(api_creds)

        wallet = client.get_address()
        logger.info(f"✅ Client CLOB initialisé | Wallet: {wallet}")

        _client = client
        return client

    except ImportError:
        logger.error("py-clob-client non installé.")
        raise
    except Exception as e:
        logger.error(f"Erreur init client CLOB: {e}")
        raise


def get_usdc_balance(client) -> float:
    try:
        # Méthode correcte selon la version actuelle du SDK
        data = client.get_balance_allowance(
            params={"asset_type": "USDC"}
        )
        balance = float(data.get("balance", 0))
        # Le SDK retourne déjà en USDC (pas en micro-unités selon la version)
        # Si la valeur semble aberrante (>1000000), diviser par 1e6
        if balance > 100000:
            balance = balance / 1e6
        logger.info(f"💰 Balance USDC: {balance:.2f}$")
        return balance
    except Exception as e:
        logger.error(f"Erreur récupération balance: {e}")
        # Fallback : retourne le bankroll config pour ne pas bloquer
        from config import BANKROLL_USDC
        logger.warning(f"Fallback balance: {BANKROLL_USDC}$")
        return BANKROLL_USDC


def get_open_positions(client) -> list[dict]:
    try:
        # L'API CLOB expose les trades, pas directement les positions
        # On récupère les trades ouverts via get_trades
        trades = client.get_trades()
        if trades is None:
            return []
        # Filtre les trades non résolus
        open_trades = [t for t in trades if t.get("status", "") not in ("RESOLVED", "CANCELLED")]
        logger.info(f"📊 {len(open_trades)} trades ouverts")
        return open_trades
    except Exception as e:
        logger.debug(f"Impossible de récupérer les trades: {e}")
        return []


def place_market_order(
    client,
    token_id: str,
    side: str,
    amount_usdc: float,
    slippage: float = 0.02,
    dry_run: bool = True
) -> Optional[dict]:
    try:
        from py_clob_client.clob_types import MarketOrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY, SELL

        side_const = BUY if side.upper() == "BUY" else SELL
        amount_raw = int(amount_usdc * 1e6)

        if dry_run:
            logger.info(
                f"[DRY RUN] 📝 Ordre simulé: {side} {amount_usdc:.2f}$ "
                f"sur token {token_id[:20]}..."
            )
            return {"status": "dry_run", "side": side, "amount_usdc": amount_usdc, "token_id": token_id}

        order_args = MarketOrderArgs(token_id=token_id, amount=amount_raw, side=side_const)
        signed_order = client.create_market_order(order_args)
        response = client.post_order(signed_order, OrderType.FOK)
        logger.info(f"✅ Ordre exécuté: {response}")
        return response

    except Exception as e:
        logger.error(f"❌ Erreur placement ordre: {e}")
        return None


def execute_opportunity(client, opportunity: dict, position_size: float, dry_run: bool = True) -> bool:
    token_id = opportunity.get("token_id")
    if not token_id or position_size < 1.0:
        logger.warning("Token manquant ou position trop petite (<1$), skip.")
        return False

    logger.info(
        f"🚀 Exécution | {opportunity.get('outcome')} @ {opportunity.get('price'):.2%} | "
        f"Edge: {opportunity.get('edge'):.2%} | Size: {position_size:.2f}$"
    )

    result = place_market_order(
        client=client, token_id=token_id, side="BUY",
        amount_usdc=position_size, dry_run=dry_run
    )

    if result:
        logger.info("✅ Trade exécuté avec succès")
        return True

    logger.error("❌ Trade échoué")
    return False


def check_and_close_positions(client, dry_run: bool = True):
    positions = get_open_positions(client)
    if not positions:
        return
    for pos in positions:
        current_price = float(pos.get("price", 0))
        avg_price = float(pos.get("avgPrice", current_price))
        pnl_pct = (current_price - avg_price) / avg_price if avg_price > 0 else 0

        if pnl_pct >= 0.50:
            logger.info(f"🎯 Take Profit: {pos.get('asset_id','')[:20]} | PnL: +{pnl_pct:.1%}")
        elif pnl_pct <= -0.30:
            logger.warning(f"🛑 Stop Loss: {pos.get('asset_id','')[:20]} | PnL: {pnl_pct:.1%}")
