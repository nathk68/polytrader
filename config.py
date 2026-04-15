import os
from dotenv import load_dotenv

load_dotenv()

# === WALLET ===
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
POLYGON_RPC = os.getenv("POLYGON_RPC", "https://polygon-rpc.com")

# === CLOB API ===
CLOB_HOST = "https://clob.polymarket.com"
GAMMA_HOST = "https://gamma-api.polymarket.com"

# === RISK MANAGEMENT ===
BANKROLL_USDC = float(os.getenv("BANKROLL_USDC", "30"))
MAX_POSITION_PCT = float(os.getenv("MAX_POSITION_PCT", "0.15"))
MIN_EDGE_THRESHOLD = float(os.getenv("MIN_EDGE_THRESHOLD", "0.06"))
MIN_VOLUME_24H = float(os.getenv("MIN_VOLUME_24H", "500"))   # Abaissé à 500$
MAX_SPREAD_PCT = float(os.getenv("MAX_SPREAD_PCT", "0.05"))
MIN_PROB = float(os.getenv("MIN_PROB", "0.55"))
MAX_PROB = float(os.getenv("MAX_PROB", "0.97"))

# === STRATEGIES ===
EXPIRY_WINDOW_DAYS = int(os.getenv("EXPIRY_WINDOW_DAYS", "30"))  # Élargi à 30 jours
SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "5"))

# === LOGGING ===
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
