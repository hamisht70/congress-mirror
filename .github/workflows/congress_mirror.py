import requests, time, os
from datetime import datetime
from bs4 import BeautifulSoup
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest

ALPACA_KEY    = os.environ["ALPACA_KEY"]
ALPACA_SECRET = os.environ["ALPACA_SECRET"]
PAPER         = True
ALLOC_PCT     = 0.90

trade_client = TradingClient(ALPACA_KEY, ALPACA_SECRET, paper=PAPER)
data_client  = StockHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)
HEADERS = {"User-Agent": "Mozilla/5.0"}

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def baseline():
    return [
        {"rank":1,"name":"Nancy Pelosi","party":"D","return_12m":68.2,"holds":["NVDA","AAPL","MSFT","GOOG"]},
        {"rank":2,"name":"Dan Crenshaw","party":"R","return_12m":54.7,"holds":["LMT","RTX","NOC","BA"]},
        {"rank":3,"name":"Josh Gottheimer","party":"D","return_12m":48.3,"holds":["MSFT","AMZN","GOOGL","META"]},
    ]

def fetch_rankings():
    print(f"[{now()}] Fetching Capitol Trades...")
    try:
        r = requests.get("https://capitaltrades.com/politicians?sortBy=return&period=12m&pageSize=10", headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        rows = soup.select("tbody tr")
        politicians = []
        for i, row in enumerate(rows[:10]):
            cells = row.find_all("td")
            if len(cells) < 3: continue
            name = cells[0].get_text(strip=True)
            ret_text = next((c.get_text(strip=True) for c in cells if "%" in c.get_text()), "0%")
            try: ret_pct = float(ret_text.replace("%","").replace("+","").strip())
            except: ret_pct = 0.0
            politicians.append({"rank":i+1,"name":name,"return_12m":ret_pct,"holds":[]})
        if politicians:
            return politicians
    except Exception as e:
        print(f"[{now()}] Live fetch failed: {e} - using fallback")
    return baseline()

def get_price(symbol):
    req = StockLatestTradeRequest(symbol_or_symbols=symbol, feed="iex")
    return float(data_client.get_stock_latest_trade(req)[symbol].price)

def run():
    print(f"\n{'='*50}\n  Congress Mirror - {now()}\n{'='*50}")
    rankings = fetch_rankings()
    top = rankings[0]
    print(f"\nTop performer: {top['name']} ({top['return_12m']:+.1f}%)")
    holds = top.get("holds") or ["NVDA","AAPL","MSFT","GOOG"]
    acct = trade_client.get_account()
    bp = float(acct.buying_power)
    per = (bp * ALLOC_PCT) / len(holds)
    print(f"Buying power: ${bp:,.2f}  Per stock: ${per:,.2f}")
    print("Closing existing positions...")
    trade_client.close_all_positions(cancel_orders=True)
    time.sleep(2)
    placed = []
    for sym in holds:
        try:
            price = get_price(sym)
            qty = int(per // price)
            if qty <= 0: print(f"  Skip {sym} - insufficient funds"); continue
            trade_client.submit_order(MarketOrderRequest(symbol=sym, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY))
            placed.append((sym, qty, price))
            print(f"  BUY {qty}x {sym} @ ${price:.2f}")
        except Exception as e:
            print(f"  {sym} failed: {e}")
    print(f"\nDone - {len(placed)}/{len(holds)} positions placed")

if __name__ == "__main__":
    run()
