# ================================================================
#  LCH v5 BOT — CONFIG (Telegram Only Edition)
#  Sirf yeh 2 cheezein fill karo aur bot ready hai.
# ================================================================

# ----------------------------------------------------------------
#  TELEGRAM SETTINGS  ← Sirf yahi chahiye
# ----------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8975592206:AAHd4vG3wAHuugpsXjhV7giiyY718X_0tlc"
# Example: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
# Kaise banao: Telegram pe @BotFather -> /newbot

TELEGRAM_CHAT_ID   = "1442051354"
# Example: "123456789"
# Kaise pata karo: Telegram pe @userinfobot -> start karo

# ----------------------------------------------------------------
#  TRADING PAIR
# ----------------------------------------------------------------
SYMBOL             = "BTC/USDT"
TIMEFRAME          = "15m"
EXCHANGE           = "binance"

# ----------------------------------------------------------------
#  STRATEGY PARAMETERS (Pine Script v5 defaults)
# ----------------------------------------------------------------
SWING_LB           = 12
ZONE_ATR_MULT      = 0.55
MIN_ZONE_AGE       = 15
MIN_SCORE          = 3
RSI_LEN            = 14
DIV_LB             = 6
MIN_WICK_RATIO     = 0.42
VOL_MULT           = 1.8
ADX_THRESH         = 28
MIN_RR_VWAP        = 1.0
HTF_EMA_LEN        = 21
ATR_LEN            = 14
SL_ATR_MULT        = 0.5
TP1_RR             = 1.5
TP2_RR             = 3.0
TP3_RR             = 6.0
COOLDOWN_BARS      = 8

# ----------------------------------------------------------------
#  BOT SETTINGS
# ----------------------------------------------------------------
CHECK_INTERVAL_SEC = 60
SEND_TELEGRAM      = True
LOG_TO_FILE        = True

