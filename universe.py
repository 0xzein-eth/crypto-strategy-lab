"""Frozen, auditable crypto paper-research universe (v2).
No unaudited auto-listing; missing instruments are skipped, never fabricated.
Sector labels are research groupings, not independent market factors.
"""
ASSET_SECTORS = {
    "BTC": "major", "ETH": "major", "SOL": "major", "BNB": "major", "XRP": "payments",
    "ADA": "layer1", "DOGE": "meme", "LINK": "oracle", "AVAX": "layer1",
    "SUI": "layer1", "LTC": "payments", "TRX": "payments",
    "DOT": "layer1", "UNI": "defi", "AAVE": "defi", "NEAR": "layer1",
    "ATOM": "layer1", "ARB": "layer2", "OP": "layer2", "INJ": "defi",
    "APT": "layer1", "FIL": "infrastructure", "PEPE": "meme",
    "WIF": "meme", "TON": "layer1", "ETC": "layer1", "BCH": "payments",
    "XLM": "payments", "HBAR": "layer1", "SEI": "layer1", "ICP": "infrastructure",
    "ALGO": "layer1", "RUNE": "defi", "JUP": "defi", "SHIB": "meme",
    "CRV": "defi", "GRT": "infrastructure", "POL": "layer2",
}
# Static, versioned: newly listed venues/derivatives must be observed from the provider.
SYMBOLS = tuple(ASSET_SECTORS)
UNIVERSE_VERSION = "2026-10-08-v2"

def sector(symbol):
    return ASSET_SECTORS[symbol]

def bucket(symbol, price_change_pct, turnover):
    """Predeclared sampler strata: sector, direction and volatility band."""
    return (
        sector(symbol),
        "rising" if price_change_pct >= 0 else "falling",
        "volatile" if abs(price_change_pct)>=3 else "moderate",
    )
