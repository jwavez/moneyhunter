"""SQLite ledger: buys, sales, expenses, capital top-ups, and an append-only audit log."""
import os, sqlite3, datetime as dt

DB = os.getenv("MONEYHUNTER_DB", os.path.join(os.path.dirname(__file__), "..", "data", "ledger.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, title TEXT, category TEXT, buy_date TEXT,
  buy_cost REAL, source TEXT, url TEXT, plan_target REAL, plan_floor REAL, status TEXT DEFAULT 'bought',
  sell_date TEXT, sale_price REAL, platform TEXT, fees REAL, postage REAL, packaging REAL, notes TEXT);
CREATE TABLE IF NOT EXISTS cash(id INTEGER PRIMARY KEY, date TEXT, kind TEXT, amount REAL, note TEXT);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, ts TEXT, action TEXT, detail TEXT);
"""

def conn():
    c = sqlite3.connect(DB); c.executescript(SCHEMA); return c

def _audit(c, action, detail):
    c.execute("INSERT INTO audit(ts,action,detail) VALUES(?,?,?)", (dt.datetime.now().isoformat(timespec="seconds"), action, detail))

def add_capital(amount, note="top-up", date=None):
    with conn() as c:
        c.execute("INSERT INTO cash(date,kind,amount,note) VALUES(?,?,?,?)", (date or dt.date.today().isoformat(), "capital", amount, note))
        _audit(c, "capital", f"{amount} {note}")

def add_expense(amount, note, date=None):
    with conn() as c:
        c.execute("INSERT INTO cash(date,kind,amount,note) VALUES(?,?,?,?)", (date or dt.date.today().isoformat(), "expense", amount, note))
        _audit(c, "expense", f"{amount} {note}")

def buy(title, category, cost, source="", url="", target=None, floor=None, date=None):
    with conn() as c:
        cur = c.execute("INSERT INTO items(title,category,buy_date,buy_cost,source,url,plan_target,plan_floor) VALUES(?,?,?,?,?,?,?,?)",
                        (title, category, date or dt.date.today().isoformat(), cost, source, url, target, floor))
        _audit(c, "buy", f"#{cur.lastrowid} {title} £{cost}")
        return cur.lastrowid

def sell(item_id, price, platform, fees, postage, packaging=0.5, date=None, notes=""):
    with conn() as c:
        c.execute("UPDATE items SET status='sold', sell_date=?, sale_price=?, platform=?, fees=?, postage=?, packaging=?, notes=? WHERE id=?",
                  (date or dt.date.today().isoformat(), price, platform, fees, postage, packaging, notes, item_id))
        _audit(c, "sell", f"#{item_id} £{price} on {platform}")

def tax_year_start(d: dt.date) -> dt.date:
    y = d.year if (d.month, d.day) >= (4, 6) else d.year - 1
    return dt.date(y, 4, 6)

def summary(today=None):
    today = today or dt.date.today()
    with conn() as c:
        cap = c.execute("SELECT COALESCE(SUM(amount),0) FROM cash WHERE kind='capital'").fetchone()[0]
        exp = c.execute("SELECT COALESCE(SUM(amount),0) FROM cash WHERE kind='expense'").fetchone()[0]
        spent = c.execute("SELECT COALESCE(SUM(buy_cost),0) FROM items").fetchone()[0]
        stock = c.execute("SELECT COALESCE(SUM(buy_cost),0), COUNT(*) FROM items WHERE status!='sold'").fetchone()
        sold = c.execute("SELECT COALESCE(SUM(sale_price),0), COALESCE(SUM(sale_price-fees-postage-packaging-buy_cost),0), COUNT(*) FROM items WHERE status='sold'").fetchone()
        receipts_net = c.execute("SELECT COALESCE(SUM(sale_price-fees-postage-packaging),0) FROM items WHERE status='sold'").fetchone()[0]
        tys = tax_year_start(today).isoformat()
        gross_ty = c.execute("SELECT COALESCE(SUM(sale_price),0) FROM items WHERE status='sold' AND sell_date>=?", (tys,)).fetchone()[0]
        year = str(today.year)
        per_plat = c.execute("SELECT platform, COUNT(*), SUM(sale_price) FROM items WHERE status='sold' AND substr(sell_date,1,4)=? GROUP BY platform", (year,)).fetchall()
    cash = cap - spent + receipts_net - exp
    bankroll = cash + stock[0]
    return {"capital_in": cap, "cash": round(cash, 2), "stock_cost": stock[0], "open_items": stock[1],
            "bankroll": round(bankroll, 2), "sold_count": sold[2], "gross_sales": sold[0],
            "realised_profit": round(sold[1] - exp, 2), "gross_tax_year": gross_ty,
            "platform_year": [{"platform": p, "sales": n, "value": v} for p, n, v in per_plat]}

def assessment_period(start: str, end: str):
    """Receipts and expenses inside a UC monthly assessment period (inclusive)."""
    with conn() as c:
        rec = c.execute("SELECT COALESCE(SUM(sale_price),0) FROM items WHERE status='sold' AND sell_date BETWEEN ? AND ?", (start, end)).fetchone()[0]
        stock = c.execute("SELECT COALESCE(SUM(buy_cost),0) FROM items WHERE buy_date BETWEEN ? AND ?", (start, end)).fetchone()[0]
        sell_costs = c.execute("SELECT COALESCE(SUM(fees+postage+packaging),0) FROM items WHERE status='sold' AND sell_date BETWEEN ? AND ?", (start, end)).fetchone()[0]
        other = c.execute("SELECT COALESCE(SUM(amount),0) FROM cash WHERE kind='expense' AND date BETWEEN ? AND ?", (start, end)).fetchone()[0]
    return {"receipts": rec, "expenses": round(stock + sell_costs + other, 2)}

def streak(today=None) -> int:
    """Consecutive days (ending today or yesterday) with a buy or sale."""
    today = today or dt.date.today()
    with conn() as c:
        days = {r[0][:10] for r in c.execute("SELECT ts FROM audit WHERE action IN ('buy','sell')")}
    n, d = 0, today
    if d.isoformat() not in days: d -= dt.timedelta(days=1)
    while d.isoformat() in days:
        n += 1; d -= dt.timedelta(days=1)
    return n
