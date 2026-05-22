"""
================================================================
 LCH v5 BOT — Liquidation Cascade Hunt (Python Edition)
 Same logic as Pine Script v5 | Unlimited FREE alerts
 Data   : Binance public API (no account needed)
 Alerts : Telegram bot (free) + Gmail (free)
 Runs   : Your PC, or any free cloud (Railway / Render)
================================================================
"""

import time
import logging
import requests
import traceback
from datetime import datetime, timezone

import ccxt
import pandas as pd
import numpy as np
import ta

import config as cfg

# ----------------------------------------------------------------
#  LOGGING
# ----------------------------------------------------------------
handlers = [logging.StreamHandler()]
if cfg.LOG_TO_FILE:
    handlers.append(logging.FileHandler("lch_bot.log", encoding="utf-8"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=handlers,
)
log = logging.getLogger("LCH_v5")

# ================================================================
#  ALERTS
# ================================================================

def send_telegram(message: str) -> None:
    """Send message to Telegram bot."""
    if not cfg.SEND_TELEGRAM:
        return
    url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": cfg.TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            log.info("Telegram alert sent")
        else:
            log.warning(f"Telegram error: {r.status_code} {r.text[:100]}")
    except Exception as e:
        log.error(f"Telegram exception: {e}")


# Gmail removed - Telegram only


def alert(subject: str, body: str) -> None:
    """Fire Telegram alert only."""
    log.info(f"ALERT: {subject}")
    full_msg = f"<b>{subject}</b>\n\n{body}"
    send_telegram(full_msg)

# ================================================================
#  DATA FETCH
# ================================================================

exchange = ccxt.okx({"enableRateLimit": True})

def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 300) -> pd.DataFrame:
    """Fetch OHLCV from Binance, return DataFrame."""
    raw = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df  = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df.set_index("ts", inplace=True)
    return df.astype(float)


def fetch_htf(symbol: str, limit: int = 100) -> pd.DataFrame:
    """Fetch 1H bars for HTF EMA."""
    return fetch_ohlcv(symbol, "1h", limit)


def fetch_4h(symbol: str, limit: int = 60) -> pd.DataFrame:
    """Fetch 4H bars for macro EMA."""
    return fetch_ohlcv(symbol, "4h", limit)

# ================================================================
#  INDICATORS
# ================================================================

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # RSI
    df["rsi"]     = ta.momentum.RSIIndicator(df["close"], window=cfg.RSI_LEN).rsi()
    # ATR
    df["atr"]     = ta.volatility.AverageTrueRange(
                        df["high"], df["low"], df["close"],
                        window=cfg.ATR_LEN).average_true_range()
    # EMA
    df["ema21"]   = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator()
    df["ema50"]   = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
    # ADX
    adx_ind       = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
    df["adx"]     = adx_ind.adx()
    # VWAP  (intraday reset: use rolling 96-bar proxy = ~24h on 15m)
    tp            = (df["high"] + df["low"] + df["close"]) / 3
    cum_vol       = df["volume"].cumsum()
    cum_tpvol     = (tp * df["volume"]).cumsum()
    df["vwap"]    = cum_tpvol / cum_vol
    # CVD
    df["cvd_bar"] = df["volume"].where(df["close"] >= df["open"], -df["volume"])
    df["cvd"]     = df["cvd_bar"].cumsum()
    # Volume SMA
    df["vol_sma"] = df["volume"].rolling(20).mean()
    return df


def swing_pivots(df: pd.DataFrame, lb: int):
    """Return last swing high and low levels."""
    n         = len(df)
    sup_level = np.nan
    res_level = np.nan
    sup_idx   = np.nan
    res_idx   = np.nan

    for i in range(lb, n - lb):
        # Pivot high
        if df["high"].iloc[i] == df["high"].iloc[i-lb:i+lb+1].max():
            res_level = df["high"].iloc[i]
            res_idx   = i
        # Pivot low
        if df["low"].iloc[i] == df["low"].iloc[i-lb:i+lb+1].min():
            sup_level = df["low"].iloc[i]
            sup_idx   = i

    sup_age = (n - 1) - sup_idx if not np.isnan(sup_idx) else np.nan
    res_age = (n - 1) - res_idx if not np.isnan(res_idx) else np.nan

    # HVN: check if pivot bar had 1.5x avg volume
    sup_hvn = False
    res_hvn = False
    if not np.isnan(sup_idx):
        idx = int(sup_idx)
        avg = df["vol_sma"].iloc[idx]
        sup_hvn = df["volume"].iloc[idx] >= avg * 1.5 if avg > 0 else False
    if not np.isnan(res_idx):
        idx = int(res_idx)
        avg = df["vol_sma"].iloc[idx]
        res_hvn = df["volume"].iloc[idx] >= avg * 1.5 if avg > 0 else False

    return sup_level, res_level, sup_age, res_age, sup_hvn, res_hvn


def detect_fvg(df: pd.DataFrame):
    """Detect most recent bullish and bearish Fair Value Gap."""
    bull_hi, bull_lo = np.nan, np.nan
    bear_hi, bear_lo = np.nan, np.nan
    for i in range(2, len(df)):
        # Bullish FVG: candle[i].low > candle[i-2].high
        if df["low"].iloc[i] > df["high"].iloc[i-2]:
            bull_hi = df["low"].iloc[i]
            bull_lo = df["high"].iloc[i-2]
        # Bearish FVG: candle[i].high < candle[i-2].low
        if df["high"].iloc[i] < df["low"].iloc[i-2]:
            bear_hi = df["low"].iloc[i-2]
            bear_lo = df["high"].iloc[i]
    return bull_hi, bull_lo, bear_hi, bear_lo


def prev_day_hl(df: pd.DataFrame):
    """Previous calendar day high and low."""
    df_d     = df.resample("1D").agg({"high": "max", "low": "min"})
    if len(df_d) < 2:
        return np.nan, np.nan
    pdh = df_d["high"].iloc[-2]
    pdl = df_d["low"].iloc[-2]
    return pdh, pdl


def prev_week_hl(df: pd.DataFrame):
    """Previous calendar week high and low."""
    df_w = df.resample("1W").agg({"high": "max", "low": "min"})
    if len(df_w) < 2:
        return np.nan, np.nan
    pwh = df_w["high"].iloc[-2]
    pwl = df_w["low"].iloc[-2]
    return pwh, pwl


def round_levels(price: float, zone_w: float):
    """Check proximity to $1K and $5K round numbers."""
    r1k = round(price / 1000) * 1000
    r5k = round(price / 5000) * 5000
    near_1k = abs(price - r1k) <= zone_w * 2.5
    near_5k = abs(price - r5k) <= zone_w * 2.5
    return near_1k or near_5k

# ================================================================
#  DIVERGENCE HELPERS
# ================================================================

def bull_rsi_div(df: pd.DataFrame, lb: int) -> bool:
    """Bullish RSI divergence: price new low, RSI higher low."""
    if len(df) < lb + 1:
        return False
    recent = df.iloc[-(lb+1):-1]
    cur    = df.iloc[-1]
    return (cur["low"]  < recent["low"].min() and
            cur["rsi"]  > recent["rsi"].min())


def bear_rsi_div(df: pd.DataFrame, lb: int) -> bool:
    """Bearish RSI divergence: price new high, RSI lower high."""
    if len(df) < lb + 1:
        return False
    recent = df.iloc[-(lb+1):-1]
    cur    = df.iloc[-1]
    return (cur["high"] > recent["high"].max() and
            cur["rsi"]  < recent["rsi"].max())


def bull_cvd_div(df: pd.DataFrame, lb: int) -> bool:
    """Bullish CVD divergence: price new low, CVD higher."""
    if len(df) < lb + 1:
        return False
    recent = df.iloc[-(lb+1):-1]
    cur    = df.iloc[-1]
    return (cur["low"] < recent["low"].min() and
            cur["cvd"] > recent["cvd"].min())


def bear_cvd_div(df: pd.DataFrame, lb: int) -> bool:
    """Bearish CVD divergence: price new high, CVD lower."""
    if len(df) < lb + 1:
        return False
    recent = df.iloc[-(lb+1):-1]
    cur    = df.iloc[-1]
    return (cur["high"] > recent["high"].max() and
            cur["cvd"]  < recent["cvd"].max())

# ================================================================
#  SESSION CHECK (UTC)
# ================================================================

def in_session(dt: datetime) -> bool:
    """London 0800-1700 UTC or NY 1300-2100 UTC."""
    h = dt.hour
    london = 8  <= h < 17
    ny     = 13 <= h < 21
    return london or ny

# ================================================================
#  CORE SIGNAL LOGIC
# ================================================================

def compute_signal(df15: pd.DataFrame, df1h: pd.DataFrame, df4h: pd.DataFrame):
    """
    Run the full LCH v5 filter stack on the latest closed 15M bar.
    Returns (direction, levels_dict) where direction is 'long', 'short', or None.
    """
    # Need enough bars
    if len(df15) < 100:
        log.warning("Not enough bars yet")
        return None, {}

    df15 = compute_indicators(df15)
    bar  = df15.iloc[-1]      # latest CLOSED bar
    prev = df15.iloc[-2]
    now  = bar.name.to_pydatetime()

    # -- Session check --
    if not in_session(now):
        log.debug("Outside session")
        return None, {}

    # -- HTF EMA --
    ema_1h_val = ta.trend.EMAIndicator(df1h["close"], window=cfg.HTF_EMA_LEN).ema_indicator().iloc[-1]
    ema_4h_val = ta.trend.EMAIndicator(df4h["close"], window=cfg.HTF_EMA_LEN).ema_indicator().iloc[-1]

    price  = bar["close"]
    atr    = bar["atr"]
    zone_w = atr * cfg.ZONE_ATR_MULT

    # -- Cluster zones --
    sup, res, sup_age, res_age, sup_hvn, res_hvn = swing_pivots(df15, cfg.SWING_LB)
    pdh, pdl = prev_day_hl(df15)
    pwh, pwl = prev_week_hl(df15)
    near_rnd  = round_levels(price, zone_w)
    at_100    = abs(price - round(price / 100) * 100) <= zone_w * 3.0  # for Gold; ignored on BTC but harmless

    # FVG
    bull_fvg_hi, bull_fvg_lo, bear_fvg_hi, bear_fvg_lo = detect_fvg(df15)

    def in_zone(level, z_w):
        return (not np.isnan(level) and
                bar["high"] >= level - z_w and
                bar["low"]  <= level + z_w)

    # Long cluster raw
    hit_sup_sw  = in_zone(sup, zone_w)
    hit_sup_pdl = in_zone(pdl, zone_w) if not np.isnan(pdl) else False
    hit_sup_pwl = in_zone(pwl, zone_w) if not np.isnan(pwl) else False
    cluster_l   = hit_sup_sw or hit_sup_pdl or hit_sup_pwl

    # Short cluster raw
    hit_res_sw  = in_zone(res, zone_w)
    hit_res_pdh = in_zone(pdh, zone_w) if not np.isnan(pdh) else False
    hit_res_pwh = in_zone(pwh, zone_w) if not np.isnan(pwh) else False
    cluster_s   = hit_res_sw or hit_res_pdh or hit_res_pwh

    if not cluster_l and not cluster_s:
        log.debug("No cluster hit")
        return None, {}

    # -- FVG at cluster --
    fvg_at_sup = (not np.isnan(bull_fvg_lo) and
                  not np.isnan(sup) and
                  sup >= bull_fvg_lo and sup <= bull_fvg_hi)

    fvg_at_res = (not np.isnan(bear_fvg_lo) and
                  not np.isnan(res) and
                  res >= bear_fvg_lo and res <= bear_fvg_hi)

    # -- Cluster scoring --
    def score_long():
        s = 0
        if hit_sup_sw or hit_sup_pdl: s += 1
        if hit_sup_pwl:               s += 1
        if near_rnd:                  s += 1
        if sup_hvn:                   s += 1
        if fvg_at_sup:                s += 1
        return s

    def score_short():
        s = 0
        if hit_res_sw or hit_res_pdh: s += 1
        if hit_res_pwh:               s += 1
        if near_rnd:                  s += 1
        if res_hvn:                   s += 1
        if fvg_at_res:                s += 1
        return s

    sc_l = score_long()
    sc_s = score_short()

    # -- Zone maturity + second touch --
    c40_high = df15["close"].iloc[-40:].max()
    c40_low  = df15["close"].iloc[-40:].min()

    mature_l  = (not np.isnan(sup_age)) and sup_age >= cfg.MIN_ZONE_AGE
    mature_s  = (not np.isnan(res_age)) and res_age >= cfg.MIN_ZONE_AGE
    touch2_l  = mature_l and (not np.isnan(sup)) and c40_high > sup + zone_w * 2.0
    touch2_s  = mature_s and (not np.isnan(res)) and c40_low  < res - zone_w * 2.0

    # -- Candle metrics --
    candle_range = bar["high"] - bar["low"]
    lower_wick   = min(bar["open"], bar["close"]) - bar["low"]
    upper_wick   = bar["high"] - max(bar["open"], bar["close"])
    body_size    = abs(bar["close"] - bar["open"])

    wick_l = (candle_range > atr * 0.15 and
              lower_wick / candle_range >= cfg.MIN_WICK_RATIO)
    wick_s = (candle_range > atr * 0.15 and
              upper_wick / candle_range >= cfg.MIN_WICK_RATIO)

    # Reversal pattern: engulf or pin bar
    prev_top    = max(prev["open"], prev["close"])
    prev_bot    = min(prev["open"], prev["close"])
    bull_engulf = bar["close"] > prev_top
    bear_engulf = bar["close"] < prev_bot
    bull_pin    = (bar["close"] >= bar["low"] + candle_range * 0.75 and
                   lower_wick >= body_size * 2.0 and
                   bar["close"] > bar["open"])
    bear_pin    = (bar["close"] <= bar["high"] - candle_range * 0.75 and
                   upper_wick >= body_size * 2.0 and
                   bar["close"] < bar["open"])
    pattern_l   = bull_engulf or bull_pin
    pattern_s   = bear_engulf or bear_pin

    # Zone recovery
    recovery_l = (not np.isnan(sup) and bar["close"] >= sup - zone_w * 0.3)
    recovery_s = (not np.isnan(res) and bar["close"] <= res + zone_w * 0.3)

    # Divergences
    rsi_div_l = bull_rsi_div(df15, cfg.DIV_LB)
    rsi_div_s = bear_rsi_div(df15, cfg.DIV_LB)
    cvd_div_l = bull_cvd_div(df15, cfg.DIV_LB)
    cvd_div_s = bear_cvd_div(df15, cfg.DIV_LB)

    # Volume 2-bar
    vol_2bar     = bar["volume"] + prev["volume"]
    vol_sma_2bar = bar["vol_sma"] + prev["vol_sma"]
    vol_ok       = vol_2bar >= vol_sma_2bar * cfg.VOL_MULT

    # ADX
    adx_ok = bar["adx"] < cfg.ADX_THRESH

    # HTF trend
    trend_l = price > ema_4h_val and price > ema_1h_val
    trend_s = price < ema_4h_val and price < ema_1h_val

    # SL computation
    sup_safe    = sup if not np.isnan(sup) else bar["low"]
    res_safe    = res if not np.isnan(res) else bar["high"]

    long_sl_raw = min(sup_safe - zone_w - atr * cfg.SL_ATR_MULT,
                      bar["low"] - atr * 0.2)
    long_sl     = min(long_sl_raw, price - atr * 0.5)
    if fvg_at_sup and not np.isnan(bull_fvg_lo):
        long_sl = min(long_sl, bull_fvg_lo - atr * 0.3)
    long_risk   = max(price - long_sl, atr * 0.2)
    long_tp1    = price + long_risk * cfg.TP1_RR
    long_tp2    = price + long_risk * cfg.TP2_RR
    long_tp3    = price + long_risk * cfg.TP3_RR

    short_sl_raw = max(res_safe + zone_w + atr * cfg.SL_ATR_MULT,
                       bar["high"] + atr * 0.2)
    short_sl     = max(short_sl_raw, price + atr * 0.5)
    if fvg_at_res and not np.isnan(bear_fvg_hi):
        short_sl = max(short_sl, bear_fvg_hi + atr * 0.3)
    short_risk   = max(short_sl - price, atr * 0.2)
    short_tp1    = price - short_risk * cfg.TP1_RR
    short_tp2    = price - short_risk * cfg.TP2_RR
    short_tp3    = price - short_risk * cfg.TP3_RR

    # Clear path
    path_ok_l = np.isnan(res) or res > long_tp2  or res < bar["low"]
    path_ok_s = np.isnan(sup) or sup < short_tp2 or sup > bar["high"]

    # R:R to VWAP
    vwap = bar["vwap"]
    rr_l = (vwap - price) / long_risk  if long_risk  > 0 else 0
    rr_s = (price - vwap) / short_risk if short_risk > 0 else 0
    rr_ok_l = vwap > price and rr_l >= cfg.MIN_RR_VWAP
    rr_ok_s = vwap < price and rr_s >= cfg.MIN_RR_VWAP

    # ============================================================
    #  FINAL SIGNAL EVALUATION
    # ============================================================
    def heatmap_note(score):
        if score >= 5: return "Heatmap: Optional (5/5) - skip check"
        if score >= 4: return "Heatmap: Quick 30-sec check (4/5)"
        return "Heatmap: Verify on Coinglass (3/5)"

    long_ok = (cluster_l and sc_l >= cfg.MIN_SCORE and touch2_l and
               wick_l and pattern_l and recovery_l and
               rsi_div_l and cvd_div_l and vol_ok and
               trend_l and adx_ok and path_ok_l and rr_ok_l)

    short_ok = (cluster_s and sc_s >= cfg.MIN_SCORE and touch2_s and
                wick_s and pattern_s and recovery_s and
                rsi_div_s and cvd_div_s and vol_ok and
                trend_s and adx_ok and path_ok_s and rr_ok_s)

    if long_ok:
        return "long", {
            "score": sc_l, "entry": price,
            "sl": round(long_sl, 2), "tp1": round(long_tp1, 2),
            "tp2": round(long_tp2, 2), "tp3": round(long_tp3, 2),
            "rsi": round(bar["rsi"], 1), "adx": round(bar["adx"], 1),
            "fvg": fvg_at_sup, "heatmap": heatmap_note(sc_l),
            "time": str(now),
        }

    if short_ok:
        return "short", {
            "score": sc_s, "entry": price,
            "sl": round(short_sl, 2), "tp1": round(short_tp1, 2),
            "tp2": round(short_tp2, 2), "tp3": round(short_tp3, 2),
            "rsi": round(bar["rsi"], 1), "adx": round(bar["adx"], 1),
            "fvg": fvg_at_res, "heatmap": heatmap_note(sc_s),
            "time": str(now),
        }

    return None, {}

# ================================================================
#  ALERT MESSAGE BUILDER
# ================================================================

def build_message(direction: str, lvl: dict) -> tuple:
    arrow  = "GREEN UP" if direction == "long" else "RED DOWN"
    side   = "LONG" if direction == "long" else "SHORT"
    fvg    = "YES" if lvl.get("fvg") else "No"
    line   = "-" * 34

    subject = f"LCH v5 BTC -- {side} SIGNAL [{lvl['score']}/5]"
    body = (
        f"LCH v5 BTC -- {side} [{arrow}]\n"
        f"{line}\n"
        f"Pair   : BTCUSDT | 15M\n"
        f"Score  : {lvl['score']}/5\n"
        f"FVG    : {fvg}\n"
        f"{line}\n"
        f"Entry  : {lvl['entry']}\n"
        f"SL     : {lvl['sl']}  (structural)\n"
        f"TP1    : {lvl['tp1']}  (1.5R | 25%)\n"
        f"TP2    : {lvl['tp2']}  (3.0R | 35%)\n"
        f"TP3    : {lvl['tp3']}  (6.0R | 40%)\n"
        f"{line}\n"
        f"RSI    : {lvl['rsi']} | ADX: {lvl['adx']}\n"
        f"{lvl['heatmap']}\n"
        f"{line}\n"
        f"Time   : {lvl['time']}\n"
        f"\n"
        f"REMINDER: After TP1 hit, move SL to breakeven!"
    )
    return subject, body

# ================================================================
#  MAIN LOOP
# ================================================================

def main():
    log.info("=" * 50)
    log.info("LCH v5 Bot starting...")
    log.info(f"Pair: {cfg.SYMBOL} | TF: {cfg.TIMEFRAME}")
    log.info(f"Telegram alerts: {'ON' if cfg.SEND_TELEGRAM else 'OFF'}")
    log.info("=" * 50)

    # Startup test message
    alert(
        "LCH v5 Bot Started",
        f"Bot is running.\nPair: {cfg.SYMBOL} | TF: {cfg.TIMEFRAME}\nTelegram alerts active. Waiting for signals..."
    )

    last_signal_bar = None   # track last alerted bar timestamp

    while True:
        try:
            # Fetch data
            df15 = fetch_ohlcv(cfg.SYMBOL, cfg.TIMEFRAME, limit=300)
            df1h = fetch_htf(cfg.SYMBOL, limit=100)
            df4h = fetch_4h(cfg.SYMBOL, limit=60)

            # Use second-to-last bar (last bar may be incomplete)
            df15_closed = df15.iloc[:-1]

            cur_bar_ts = str(df15_closed.index[-1])

            # Skip if already alerted this bar
            if cur_bar_ts == last_signal_bar:
                time.sleep(cfg.CHECK_INTERVAL_SEC)
                continue

            direction, levels = compute_signal(df15_closed, df1h, df4h)

            if direction:
                subject, body = build_message(direction, levels)
                alert(subject, body)
                last_signal_bar = cur_bar_ts
                log.info(f"Signal: {direction.upper()} | Score: {levels['score']}/5")
            else:
                log.info(f"No signal | BTC: {df15_closed['close'].iloc[-1]:.1f} | Bar: {cur_bar_ts}")

        except ccxt.NetworkError as e:
            log.warning(f"Network error (retrying): {e}")
        except ccxt.ExchangeError as e:
            log.error(f"Exchange error: {e}")
        except Exception:
            log.error(f"Unexpected error:\n{traceback.format_exc()}")

        time.sleep(cfg.CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    main()
