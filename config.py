import os
from dotenv import load_dotenv

load_dotenv()

# === WALLET ===
PRIVATE_KEY = os.getenv("PRIVATE_KEY")          # Clé privée Polygon (sans 0x)
POLYGON_RPC = os.getenv("POLYGON_RPC", "https://polygon-rpc.com")

# === CLOB API ===
CLOB_HOST = "https://clob.polymarket.com"
GAMMA_HOST = "https://gamma-api.polymarket.com"  # API metadata marchés

# === RISK MANAGEMENT ===
BANKROLL_USDC = float(os.getenv("BANKROLL_USDC", "20"))    # Capital total en $
MAX_POSITION_PCT = float(os.getenv("MAX_POSITION_PCT", "0.15"))  # Max 15% par trade
MIN_EDGE_THRESHOLD = float(os.getenv("MIN_EDGE_THRESHOLD", "0.06"))  # Edge min 6%
MIN_VOLUME_24H = float(os.getenv("MIN_VOLUME_24H", "1000"))  # Volume min $1000
MAX_SPREAD_PCT = float(os.getenv("MAX_SPREAD_PCT", "0.05"))  # Spread max 5%
MIN_PROB = float(os.getenv("MIN_PROB", "0.70"))  # Proba min pour "sûr"
MAX_PROB = float(os.getenv("MAX_PROB", "0.97"))  # Proba max (éviter 99%+)

# === STRATEGIES ===
EXPIRY_WINDOW_DAYS = int(os.getenv("EXPIRY_WINDOW_DAYS", "7"))  # J-7 max
SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "15"))  # Scan toutes les 15min

# === LOGGING ===
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
