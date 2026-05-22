"""
================================================================
 LCH GOLD BOT - Liquidation Cascade Hunt (XAUUSD Edition)
 Better than V5 for Gold with 2 extra filters:
 1. Economic Calendar Blackout (NFP, FOMC, CPI)
 2. DXY Correlation Check
 Data   : Yahoo Finance (free Gold + DXY data)
 Alerts : Telegram (unlimited free)
================================================================
"""

import time
import logging
import requests
import traceback
from datetime import datetime, timezone, timedelta

import yfinance as yf
import pandas as pd
import numpy as np
import ta

import gold_config as cfg

# ----------------------------------------------------------------
#  LOGGING
# ----------------------------------------------------------------
handlers = [logging.StreamHandler()]
if cfg.LOG_TO_FILE:
    handlers.append(logging.FileHandler("lch_gold.log", encoding="utf-8"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=handlers,
)
log = logging.getLogger("LCH_GOLD")

# ================================================================
#  TELEGRAM ALERT
# ================================================================

def send_telegram(message: str) -> None:
    if not cfg.SEND_TELEGRAM:
        return
    url     = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": cfg.TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            log.info("Telegram sent OK")
        else:
            log.warning(f"Telegram error: {r.status_code} {r.text[:80]}")
    except Exception as e:
        log.error(f"Telegram exception: {e}")


def alert(subject: str, body: str) -> None:
    log.info(f"ALERT: {subject}")
    send_telegram(f"<b>{subject}</b>\n\n{body}")

# ================================================================
#  DATA FETCH - Yahoo Finance (Free, no account needed)
# ================================================================

def fetch_gold(interval: str = "15m", period: str = "5d") -> pd.DataFrame:
    """Fetch XAUUSD data from Yahoo Finance."""
    ticker = yf.Ticker("GC=F")   # Gold Futures (closest to spot)
    df     = ticker.history(period=period, interval=interval)
    df     = df[["Open","High","Low","Close","Volume"]].copy()
    df.columns = ["open","high","low","close","volume"]
    df.index = pd.to_datetime(df.index, utc=True)
    return df.dropna().astype(float)


def fetch_htf_gold(interval: str = "1h", period: str = "30d") -> pd.DataFrame:
    ticker = yf.Ticker("GC=F")
    df     = ticker.history(period=period, interval=interval)
    df     = df[["Open","High","Low","Close","Volume"]].copy()
    df.columns = ["open","high","low","close","volume"]
    df.index = pd.to_datetime(df.index, utc=True)
    return df.dropna().astype(float)


def fetch_4h_gold() -> pd.DataFrame:
    ticker = yf.Ticker("GC=F")
    df     = ticker.history(period="60d", interval="1h")
    df     = df[["Open","High","Low","Close","Volume"]].copy()
    df.columns = ["open","high","low","close","volume"]
    df.index = pd.to_datetime(df.index, utc=True)
    # Resample to 4H
    df4h = df.resample("4h").agg({
        "open": "first", "high": "max",
        "low": "min",   "close": "last", "volume": "sum"
    }).dropna()
    return df4h.astype(float)


def fetch_dxy() -> float:
    """Fetch latest DXY (US Dollar Index) value."""
    try:
        ticker = yf.Ticker("DX-Y.NYB")
        hist   = ticker.history(period="2d", interval="1h")
        if len(hist) > 0:
            return float(hist["Close"].iloc[-1])
    except Exception as e:
        log.warning(f"DXY fetch failed: {e}")
    return None


def fetch_dxy_trend() -> str:
    """
    DXY trend: bullish = Gold longs risky, bearish = Gold longs safer.
    Uses 20-bar EMA on 1H DXY data.
    """
    try:
        ticker   = yf.Ticker("DX-Y.NYB")
        hist     = ticker.history(period="5d", interval="1h")
        closes   = hist["Close"].astype(float)
        ema20    = closes.ewm(span=20).mean()
        last_c   = closes.iloc[-1]
        last_ema = ema20.iloc[-1]
        if last_c > last_ema * 1.002:
            return "bullish"   # Dollar strong -> Gold bearish pressure
        elif last_c < last_ema * 0.998:
            return "bearish"   # Dollar weak -> Gold bullish pressure
        else:
            return "neutral"
    except Exception as e:
        log.warning(f"DXY trend failed: {e}")
        return "neutral"

# ================================================================
#  EXTRA FILTER 1: ECONOMIC CALENDAR BLACKOUT
#
#  Gold reacts violently to high-impact news events.
#  We skip ALL trades within 30 min before and 30 min after:
#  - NFP (Non-Farm Payrolls): 1st Friday of every month, 1330 UTC
#  - FOMC Rate Decision: check manually (approx 8x/year, 1800 UTC)
#  - CPI Data: approx monthly, 1330 UTC
#
#  Static list of known 2026 high-impact dates (UTC).
#  Update this list monthly for best results.
# ================================================================

HIGH_IMPACT_EVENTS_UTC = [
    # Format: (year, month, day, hour, minute)
    # NFP 2026
    (2026, 1,  9,  13, 30),
    (2026, 2,  6,  13, 30),
    (2026, 3,  6,  13, 30),
    (2026, 4,  3,  13, 30),
    (2026, 5,  1,  13, 30),
    (2026, 6,  5,  13, 30),
    (2026, 7,  2,  13, 30),
    (2026, 8,  7,  13, 30),
    (2026, 9,  4,  13, 30),
    (2026, 10, 2,  13, 30),
    (2026, 11, 6,  13, 30),
    (2026, 12, 4,  13, 30),
    # FOMC 2026 (approximate - verify on Investing.com)
    (2026, 1,  29, 19, 0),
    (2026, 3,  19, 18, 0),
    (2026, 5,  7,  18, 0),
    (2026, 6,  18, 18, 0),
    (2026, 7,  30, 18, 0),
    (2026, 9,  17, 18, 0),
    (2026, 11, 5,  19, 0),
    (2026, 12, 17, 19, 0),
    # CPI 2026 (approximate)
    (2026, 1,  15, 13, 30),
    (2026, 2,  12, 13, 30),
    (2026, 3,  12, 13, 30),
    (2026, 4,  10, 12, 30),
    (2026, 5,  13, 12, 30),
    (2026, 6,  11, 12, 30),
    (2026, 7,  14, 12, 30),
    (2026, 8,  12, 12, 30),
    (2026, 9,  11, 12, 30),
    (2026, 10, 13, 12, 30),
    (2026, 11, 12, 13, 30),
    (2026, 12, 10, 13, 30),
]

BLACKOUT_MINUTES = 30   # skip trades 30 min before and after event


def is_blackout_period(now: datetime) -> tuple:
    """
    Returns (True, event_name) if within blackout window,
    else (False, None).
    """
    now_utc = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    for (y, mo, d, h, mi) in HIGH_IMPACT_EVENTS_UTC:
        event_dt = datetime(y, mo, d, h, mi, tzinfo=timezone.utc)
        diff     = abs((now_utc - event_dt).total_seconds() / 60)
        if diff <= BLACKOUT_MINUTES:
            if diff < 0:
                event_type = f"upcoming in {int(-diff)} min"
            else:
                event_type = f"passed {int(diff)} min ago"
            return True, f"High-impact event ({event_type})"
    return False, None

# ================================================================
#  EXTRA FILTER 2: DXY CORRELATION
#
#  Gold and USD have strong inverse correlation.
#  DXY bullish  = dollar strengthening = Gold longs risky
#  DXY bearish  = dollar weakening    = Gold shorts risky
#
#  Rules:
#  Long setup:  DXY must be bearish or neutral (dollar weak)
#  Short setup: DXY must be bullish or neutral (dollar strong)
# ================================================================

def dxy_allows_trade(direction: str, dxy_trend: str) -> bool:
    if dxy_trend == "neutral":
        return True
    if direction == "long"  and dxy_trend == "bearish":
        return True    # Dollar weak = Gold long supported
    if direction == "short" and dxy_trend == "bullish":
        return True    # Dollar strong = Gold short supported
    return False       # DXY against trade direction - skip

# ================================================================
#  SESSION FILTER - Gold Optimized (UTC)
#  Best: London Open 0700-1000 UTC
#  Good: NY session 1300-2000 UTC
#  Avoid: Asian session (thin, fake moves on Gold)
# ================================================================

def in_gold_session(dt: datetime) -> bool:
    h = dt.hour
    london_open = 7  <= h < 10    # Best for Gold
    ny_session  = 13 <= h < 20    # Good for Gold
    return london_open or ny_session

# ================================================================
#  INDICATORS
# ================================================================

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df       = df.copy()
    df["rsi"]     = ta.momentum.RSIIndicator(df["close"], window=cfg.RSI_LEN).rsi()
    df["atr"]     = ta.volatility.AverageTrueRange(
                        df["high"], df["low"], df["close"],
                        window=cfg.ATR_LEN).average_true_range()
    df["ema21"]   = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator()
    df["ema50"]   = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
    adx_i         = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
    df["adx"]     = adx_i.adx()
    tp            = (df["high"] + df["low"] + df["close"]) / 3
    df["vwap"]    = (tp * df["volume"]).cumsum() / df["volume"].cumsum()
    df["cvd_bar"] = df["volume"].where(df["close"] >= df["open"], -df["volume"])
    df["cvd"]     = df["cvd_bar"].cumsum()
    df["vol_sma"] = df["volume"].rolling(20).mean()
    return df


def swing_pivots(df, lb):
    n = len(df)
    sup_level, res_level = np.nan, np.nan
    sup_idx,   res_idx   = np.nan, np.nan
    sup_hvn,   res_hvn   = False, False
    for i in range(lb, n - lb):
        if df["high"].iloc[i] == df["high"].iloc[i-lb:i+lb+1].max():
            res_level = df["high"].iloc[i]
            res_idx   = i
            avg = df["vol_sma"].iloc[i]
            res_hvn = df["volume"].iloc[i] >= avg * 1.5 if avg > 0 else False
        if df["low"].iloc[i] == df["low"].iloc[i-lb:i+lb+1].min():
            sup_level = df["low"].iloc[i]
            sup_idx   = i
            avg = df["vol_sma"].iloc[i]
            sup_hvn = df["volume"].iloc[i] >= avg * 1.5 if avg > 0 else False
    sup_age = (n-1) - sup_idx if not np.isnan(sup_idx) else np.nan
    res_age = (n-1) - res_idx if not np.isnan(res_idx) else np.nan
    return sup_level, res_level, sup_age, res_age, sup_hvn, res_hvn


def detect_fvg(df):
    bull_hi = bull_lo = bear_hi = bear_lo = np.nan
    for i in range(2, len(df)):
        if df["low"].iloc[i]  > df["high"].iloc[i-2]:
            bull_hi = df["low"].iloc[i]
            bull_lo = df["high"].iloc[i-2]
        if df["high"].iloc[i] < df["low"].iloc[i-2]:
            bear_hi = df["low"].iloc[i-2]
            bear_lo = df["high"].iloc[i]
    return bull_hi, bull_lo, bear_hi, bear_lo


def prev_day_hl(df):
    d = df.resample("1D").agg({"high":"max","low":"min"})
    if len(d) < 2: return np.nan, np.nan
    return d["high"].iloc[-2], d["low"].iloc[-2]


def prev_week_hl(df):
    w = df.resample("1W").agg({"high":"max","low":"min"})
    if len(w) < 2: return np.nan, np.nan
    return w["high"].iloc[-2], w["low"].iloc[-2]


def gold_round_levels(price, zone_w):
    """Gold round levels: $10, $50, $100 multiples."""
    r10  = round(price / 10)  * 10
    r50  = round(price / 50)  * 50
    r100 = round(price / 100) * 100
    near_10  = abs(price - r10)  <= zone_w * 2.0
    near_50  = abs(price - r50)  <= zone_w * 2.5
    near_100 = abs(price - r100) <= zone_w * 3.0
    return near_10 or near_50 or near_100, near_100, r100


def bull_rsi_div(df, lb):
    if len(df) < lb+1: return False
    r = df.iloc[-(lb+1):-1]
    c = df.iloc[-1]
    return c["low"] < r["low"].min() and c["rsi"] > r["rsi"].min()


def bear_rsi_div(df, lb):
    if len(df) < lb+1: return False
    r = df.iloc[-(lb+1):-1]
    c = df.iloc[-1]
    return c["high"] > r["high"].max() and c["rsi"] < r["rsi"].max()


def bull_cvd_div(df, lb):
    if len(df) < lb+1: return False
    r = df.iloc[-(lb+1):-1]
    c = df.iloc[-1]
    return c["low"] < r["low"].min() and c["cvd"] > r["cvd"].min()


def bear_cvd_div(df, lb):
    if len(df) < lb+1: return False
    r = df.iloc[-(lb+1):-1]
    c = df.iloc[-1]
    return c["high"] > r["high"].max() and c["cvd"] < r["cvd"].max()

# ================================================================
#  CORE SIGNAL LOGIC
# ================================================================

def compute_signal(df15, df1h, df4h, dxy_trend):
    if len(df15) < 100:
        log.warning("Not enough bars")
        return None, {}

    df15 = compute_indicators(df15)
    bar  = df15.iloc[-1]
    prev = df15.iloc[-2]
    now  = bar.name.to_pydatetime()

    # Session check
    if not in_gold_session(now):
        log.debug("Outside Gold session")
        return None, {}

    # Economic blackout check
    blackout, blackout_reason = is_blackout_period(now)
    if blackout:
        log.info(f"BLACKOUT: {blackout_reason} - skipping")
        return None, {}

    price  = bar["close"]
    atr    = bar["atr"]
    zone_w = atr * cfg.ZONE_ATR_MULT

    # HTF EMAs
    ema_1h = ta.trend.EMAIndicator(df1h["close"], window=cfg.HTF_EMA_LEN).ema_indicator().iloc[-1]
    ema_4h = ta.trend.EMAIndicator(df4h["close"], window=cfg.HTF_EMA_LEN).ema_indicator().iloc[-1]

    # Cluster zones
    sup, res, sup_age, res_age, sup_hvn, res_hvn = swing_pivots(df15, cfg.SWING_LB)
    pdh, pdl   = prev_day_hl(df15)
    pwh, pwl   = prev_week_hl(df15)
    near_rnd, at_100, r100 = gold_round_levels(price, zone_w)

    # FVG
    bfh, bfl, brh, brl = detect_fvg(df15)

    def in_zone(level, zw):
        return (not np.isnan(level) and
                bar["high"] >= level - zw and
                bar["low"]  <= level + zw)

    # Raw cluster hits
    hit_sup_sw  = in_zone(sup, zone_w)
    hit_sup_pdl = in_zone(pdl, zone_w) if not np.isnan(pdl) else False
    hit_sup_pwl = in_zone(pwl, zone_w) if not np.isnan(pwl) else False
    cluster_l   = hit_sup_sw or hit_sup_pdl or hit_sup_pwl

    hit_res_sw  = in_zone(res, zone_w)
    hit_res_pdh = in_zone(pdh, zone_w) if not np.isnan(pdh) else False
    hit_res_pwh = in_zone(pwh, zone_w) if not np.isnan(pwh) else False
    cluster_s   = hit_res_sw or hit_res_pdh or hit_res_pwh

    if not cluster_l and not cluster_s:
        return None, {}

    # FVG confluence
    fvg_sup = (not np.isnan(bfl) and not np.isnan(sup) and
               sup >= bfl and sup <= bfh)
    fvg_res = (not np.isnan(brl) and not np.isnan(res) and
               res >= brl and res <= brh)

    # Cluster scoring (Gold: $100 = +1 instead of HVN)
    sc_l = ((1 if (hit_sup_sw or hit_sup_pdl) else 0) +
            (1 if hit_sup_pwl else 0) +
            (1 if near_rnd else 0) +
            (1 if (sup_hvn or at_100) else 0) +
            (1 if fvg_sup else 0))

    sc_s = ((1 if (hit_res_sw or hit_res_pdh) else 0) +
            (1 if hit_res_pwh else 0) +
            (1 if near_rnd else 0) +
            (1 if (res_hvn or at_100) else 0) +
            (1 if fvg_res else 0))

    # Zone maturity + second touch
    c40_hi  = df15["close"].iloc[-40:].max()
    c40_lo  = df15["close"].iloc[-40:].min()
    mat_l   = (not np.isnan(sup_age)) and sup_age >= cfg.MIN_ZONE_AGE
    mat_s   = (not np.isnan(res_age)) and res_age >= cfg.MIN_ZONE_AGE
    touch2_l = mat_l and not np.isnan(sup) and c40_hi > sup + zone_w * 2.0
    touch2_s = mat_s and not np.isnan(res) and c40_lo < res - zone_w * 2.0

    # Candle metrics
    crange   = bar["high"] - bar["low"]
    lwick    = min(bar["open"], bar["close"]) - bar["low"]
    uwick    = bar["high"] - max(bar["open"], bar["close"])
    bsize    = abs(bar["close"] - bar["open"])

    wick_l   = crange > atr * 0.15 and (lwick / crange) >= cfg.MIN_WICK_RATIO
    wick_s   = crange > atr * 0.15 and (uwick / crange) >= cfg.MIN_WICK_RATIO

    ptop     = max(prev["open"], prev["close"])
    pbot     = min(prev["open"], prev["close"])
    b_engulf = bar["close"] > ptop
    s_engulf = bar["close"] < pbot
    b_pin    = (bar["close"] >= bar["low"] + crange * 0.75 and
                lwick >= bsize * 2.0 and bar["close"] > bar["open"])
    s_pin    = (bar["close"] <= bar["high"] - crange * 0.75 and
                uwick >= bsize * 2.0 and bar["close"] < bar["open"])
    pat_l    = b_engulf or b_pin
    pat_s    = s_engulf or s_pin

    rec_l    = not np.isnan(sup) and bar["close"] >= sup - zone_w * 0.3
    rec_s    = not np.isnan(res) and bar["close"] <= res + zone_w * 0.3

    # Divergences
    rdl  = bull_rsi_div(df15, cfg.DIV_LB)
    rds  = bear_rsi_div(df15, cfg.DIV_LB)
    cdl  = bull_cvd_div(df15, cfg.DIV_LB)
    cds  = bear_cvd_div(df15, cfg.DIV_LB)

    # Volume 2-bar
    v2   = bar["volume"] + prev["volume"]
    vs2  = bar["vol_sma"] + prev["vol_sma"]
    vok  = v2 >= vs2 * cfg.VOL_MULT

    # ADX (Gold: 32 threshold)
    adx_ok = bar["adx"] < cfg.ADX_THRESH

    # HTF trend (4H + 1H both must agree)
    trend_l = price > ema_4h and price > ema_1h
    trend_s = price < ema_4h and price < ema_1h

    # SL levels (Gold: 0.6 ATR buffer - wider for spreads)
    sup_s   = sup if not np.isnan(sup) else bar["low"]
    res_s   = res if not np.isnan(res) else bar["high"]

    lsl_raw = min(sup_s - zone_w - atr * cfg.SL_ATR_MULT, bar["low"] - atr * 0.2)
    lsl     = min(lsl_raw, price - atr * 0.5)
    if fvg_sup and not np.isnan(bfl):
        lsl = min(lsl, bfl - atr * 0.3)
    lrisk   = max(price - lsl, atr * 0.2)
    ltp1    = price + lrisk * cfg.TP1_RR
    ltp2    = price + lrisk * cfg.TP2_RR
    ltp3    = price + lrisk * cfg.TP3_RR

    ssl_raw = max(res_s + zone_w + atr * cfg.SL_ATR_MULT, bar["high"] + atr * 0.2)
    ssl     = max(ssl_raw, price + atr * 0.5)
    if fvg_res and not np.isnan(brh):
        ssl = max(ssl, brh + atr * 0.3)
    srisk   = max(ssl - price, atr * 0.2)
    stp1    = price - srisk * cfg.TP1_RR
    stp2    = price - srisk * cfg.TP2_RR
    stp3    = price - srisk * cfg.TP3_RR

    # Clear path
    path_l = np.isnan(res) or res > ltp2 or res < bar["low"]
    path_s = np.isnan(sup) or sup < stp2 or sup > bar["high"]

    # R:R to VWAP
    vwap   = bar["vwap"]
    rrl    = (vwap - price) / lrisk if lrisk > 0 else 0
    rrs    = (price - vwap) / srisk if srisk > 0 else 0
    rrok_l = vwap > price and rrl >= cfg.MIN_RR_VWAP
    rrok_s = vwap < price and rrs >= cfg.MIN_RR_VWAP

    def hmap(score):
        if score >= 5: return "Heatmap: Optional (5/5)"
        if score >= 4: return "Quick Coinglass check (4/5)"
        return "Verify Coinglass (3/5)"

    def rnd_note():
        if at_100:    return f"$100 LEVEL: {r100} (STRONGEST)"
        if near_rnd:  return "Round number zone active"
        return ""

    # ============================================================
    #  FINAL SIGNAL - All filters must pass
    # ============================================================

    # DXY correlation filter applied here
    long_ok  = (cluster_l and sc_l >= cfg.MIN_SCORE and touch2_l and
                wick_l and pat_l and rec_l and
                rdl and cdl and vok and
                trend_l and adx_ok and path_l and rrok_l and
                dxy_allows_trade("long", dxy_trend))

    short_ok = (cluster_s and sc_s >= cfg.MIN_SCORE and touch2_s and
                wick_s and pat_s and rec_s and
                rds and cds and vok and
                trend_s and adx_ok and path_s and rrok_s and
                dxy_allows_trade("short", dxy_trend))

    if long_ok:
        return "long", {
            "score": sc_l, "entry": round(price, 2),
            "sl": round(lsl, 2), "tp1": round(ltp1, 2),
            "tp2": round(ltp2, 2), "tp3": round(ltp3, 2),
            "rsi": round(bar["rsi"], 1), "adx": round(bar["adx"], 1),
            "fvg": fvg_sup, "dxy": dxy_trend,
            "heatmap": hmap(sc_l), "round": rnd_note(), "time": str(now),
        }

    if short_ok:
        return "short", {
            "score": sc_s, "entry": round(price, 2),
            "sl": round(ssl, 2), "tp1": round(stp1, 2),
            "tp2": round(stp2, 2), "tp3": round(stp3, 2),
            "rsi": round(bar["rsi"], 1), "adx": round(bar["adx"], 1),
            "fvg": fvg_res, "dxy": dxy_trend,
            "heatmap": hmap(sc_s), "round": rnd_note(), "time": str(now),
        }

    return None, {}

# ================================================================
#  ALERT MESSAGE BUILDER
# ================================================================

def build_message(direction, lvl):
    side  = "LONG" if direction == "long" else "SHORT"
    arrow = "UP" if direction == "long" else "DOWN"
    fvg   = "YES" if lvl.get("fvg") else "No"
    sep   = "-" * 34
    dxy_s = lvl.get("dxy","neutral").upper()
    rnd   = lvl.get("round","")

    subject = f"LCH GOLD -- {side} [{lvl['score']}/5]"
    body = (
        f"LCH GOLD -- {side} [{arrow}]\n"
        f"{sep}\n"
        f"Pair   : XAUUSD | 15M\n"
        f"Score  : {lvl['score']}/5\n"
        f"FVG    : {fvg}\n"
        f"DXY    : {dxy_s}\n"
        + (f"{rnd}\n" if rnd else "") +
        f"{sep}\n"
        f"Entry  : {lvl['entry']}\n"
        f"SL     : {lvl['sl']}  (structural)\n"
        f"TP1    : {lvl['tp1']}  (1.5R | 25%)\n"
        f"TP2    : {lvl['tp2']}  (3.0R | 35%)\n"
        f"TP3    : {lvl['tp3']}  (6.0R | 40%)\n"
        f"{sep}\n"
        f"RSI    : {lvl['rsi']} | ADX: {lvl['adx']}\n"
        f"{lvl['heatmap']}\n"
        f"{sep}\n"
        f"Time   : {lvl['time']}\n"
        f"\nREMINDER: After TP1 hit, move SL to breakeven!"
    )
    return subject, body

# ================================================================
#  MAIN LOOP
# ================================================================

def main():
    log.info("=" * 50)
    log.info("LCH GOLD Bot starting...")
    log.info(f"Pair: XAUUSD | TF: {cfg.TIMEFRAME}")
    log.info("Extra filters: DXY Correlation + Economic Blackout")
    log.info("=" * 50)

    alert(
        "LCH Gold Bot Started",
        "XAUUSD bot is running.\n"
        "Filters: DXY Correlation + Economic Blackout active.\n"
        "Waiting for signals..."
    )

    last_signal_bar = None

    while True:
        try:
            df15 = fetch_gold(interval=cfg.TIMEFRAME, period="5d")
            df1h = fetch_htf_gold(interval="1h", period="30d")
            df4h = fetch_4h_gold()

            df15_closed = df15.iloc[:-1]

            cur_bar_ts = str(df15_closed.index[-1])

            if cur_bar_ts == last_signal_bar:
                time.sleep(cfg.CHECK_INTERVAL_SEC)
                continue

            # Fetch DXY trend (updated every loop)
            dxy_trend = fetch_dxy_trend()
            dxy_val   = fetch_dxy()
            dxy_str   = f"{round(dxy_val,2)}" if dxy_val else "N/A"

            direction, levels = compute_signal(df15_closed, df1h, df4h, dxy_trend)

            if direction:
                subject, body = build_message(direction, levels)
                alert(subject, body)
                last_signal_bar = cur_bar_ts
            else:
                gold_price = df15_closed["close"].iloc[-1]
                log.info(
                    f"No signal | Gold: {gold_price:.2f} | "
                    f"DXY: {dxy_str} ({dxy_trend}) | Bar: {cur_bar_ts}"
                )

        except Exception:
            log.error(f"Error:\n{traceback.format_exc()}")

        time.sleep(cfg.CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    main()
