# ================================================================
#  LCH GOLD BOT - CONFIG
#  XAUUSD Edition | Telegram Only
# ================================================================

# ----------------------------------------------------------------
#  TELEGRAM - Same bot use kar sakte ho ya naya banao
# ----------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8975592206:AAHd4vG3wAHuugpsXjhV7giiyY718X_0tlc"
TELEGRAM_CHAT_ID   = "1442051354"

# ----------------------------------------------------------------
#  TRADING PAIR
# ----------------------------------------------------------------
SYMBOL             = "GC=F"      # Gold Futures (Yahoo Finance)
TIMEFRAME          = "15m"

# ----------------------------------------------------------------
#  GOLD-SPECIFIC PARAMETERS
# ----------------------------------------------------------------
SWING_LB           = 12
ZONE_ATR_MULT      = 0.45    # Tighter than BTC (cleaner structure)
MIN_ZONE_AGE       = 15
MIN_SCORE          = 3
RSI_LEN            = 14
DIV_LB             = 6
MIN_WICK_RATIO     = 0.42
VOL_MULT           = 1.6     # Lower than BTC (Gold volume sparser)
ADX_THRESH         = 32      # Higher than BTC (Gold trends longer)
MIN_RR_VWAP        = 1.0
HTF_EMA_LEN        = 21
ATR_LEN            = 14
SL_ATR_MULT        = 0.6     # Wider than BTC (Gold spreads at news)
TP1_RR             = 1.5
TP2_RR             = 3.0
TP3_RR             = 6.0

# ----------------------------------------------------------------
#  BOT SETTINGS
# ----------------------------------------------------------------
CHECK_INTERVAL_SEC = 60
SEND_TELEGRAM      = True
LOG_TO_FILE        = True

