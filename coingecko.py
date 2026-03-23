"""CoinGecko API client for fetching cryptocurrency price data."""

import aiohttp

COINGECKO_API = "https://api.coingecko.com/api/v3"

# Common symbol -> CoinGecko ID mapping (covers top tokens)
# For tokens not in this map, we search the API
SYMBOL_TO_ID: dict[str, str] = {
    "btc": "bitcoin",
    "eth": "ethereum",
    "usdt": "tether",
    "usdc": "usd-coin",
    "bnb": "binancecoin",
    "xrp": "ripple",
    "ada": "cardano",
    "doge": "dogecoin",
    "sol": "solana",
    "dot": "polkadot",
    "matic": "matic-network",
    "pol": "matic-network",
    "shib": "shiba-inu",
    "trx": "tron",
    "avax": "avalanche-2",
    "link": "chainlink",
    "uni": "uniswap",
    "atom": "cosmos",
    "ltc": "litecoin",
    "etc": "ethereum-classic",
    "xlm": "stellar",
    "algo": "algorand",
    "near": "near",
    "ftm": "fantom",
    "apt": "aptos",
    "arb": "arbitrum",
    "op": "optimism",
    "sui": "sui",
    "sei": "sei-network",
    "inj": "injective-protocol",
    "ton": "the-open-network",
    "pepe": "pepe",
    "wif": "dogwifcoin",
    "bonk": "bonk",
    "floki": "floki",
    "meme": "memecoin",
    "ai": "ai",
    "fet": "fetch-ai",
    "rndr": "render-token",
    "grt": "the-graph",
    "fil": "filecoin",
    "aave": "aave",
    "mkr": "maker",
    "crv": "curve-dao-token",
    "ldo": "lido-dao",
    "rpl": "rocket-pool",
    "sand": "the-sandbox",
    "mana": "decentraland",
    "axs": "axie-infinity",
    "imx": "immutable-x",
    "ape": "apecoin",
    "cake": "pancakeswap-token",
    "sushi": "sushi",
    "1inch": "1inch",
    "snx": "havven",
    "comp": "compound-governance-token",
    "yfi": "yearn-finance",
    "ens": "ethereum-name-service",
    "vet": "vechain",
    "egld": "elrond-erd-2",
    "hbar": "hedera-hashgraph",
    "icp": "internet-computer",
    "theta": "theta-token",
    "neo": "neo",
    "eos": "eos",
    "xtz": "tezos",
    "flow": "flow",
    "rose": "oasis-network",
    "zil": "zilliqa",
    "one": "harmony",
    "kava": "kava",
    "celo": "celo",
    "mina": "mina-protocol",
    "kas": "kaspa",
    "cfx": "conflux-token",
    "stx": "blockstack",
    "bch": "bitcoin-cash",
    "leo": "leo-token",
    "okb": "okb",
    "cro": "crypto-com-chain",
    "wbtc": "wrapped-bitcoin",
    "dai": "dai",
    "tusd": "true-usd",
    "busd": "binance-usd",
}


async def _search_coin_id(symbol: str) -> str | None:
    """Search CoinGecko for a coin ID by symbol."""
    url = f"{COINGECKO_API}/search"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params={"query": symbol}) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            coins = data.get("coins", [])
            # Find exact symbol match (case-insensitive)
            for coin in coins:
                if coin.get("symbol", "").lower() == symbol.lower():
                    return coin["id"]
            # Fallback to first result
            if coins:
                return coins[0]["id"]
            return None


async def get_coin_id(symbol: str) -> str | None:
    """Resolve a coin symbol to its CoinGecko ID."""
    symbol_lower = symbol.lower().strip()
    if symbol_lower in SYMBOL_TO_ID:
        return SYMBOL_TO_ID[symbol_lower]
    return await _search_coin_id(symbol_lower)


async def fetch_price(symbol: str) -> dict | None:
    """
    Fetch price data for a coin symbol.

    Returns dict with keys:
        name, symbol, price_usd, market_cap, volume_24h,
        change_24h, change_7d, high_24h, low_24h, rank
    Or None if not found.
    """
    coin_id = await get_coin_id(symbol)
    if not coin_id:
        return None

    url = f"{COINGECKO_API}/coins/{coin_id}"
    params = {
        "localization": "false",
        "tickers": "false",
        "community_data": "false",
        "developer_data": "false",
        "sparkline": "false",
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

    market = data.get("market_data", {})
    return {
        "name": data.get("name", "Unknown"),
        "symbol": data.get("symbol", symbol).upper(),
        "price_usd": market.get("current_price", {}).get("usd"),
        "market_cap": market.get("market_cap", {}).get("usd"),
        "volume_24h": market.get("total_volume", {}).get("usd"),
        "change_24h": market.get("price_change_percentage_24h"),
        "change_7d": market.get("price_change_percentage_7d"),
        "high_24h": market.get("high_24h", {}).get("usd"),
        "low_24h": market.get("low_24h", {}).get("usd"),
        "rank": data.get("market_cap_rank"),
    }
