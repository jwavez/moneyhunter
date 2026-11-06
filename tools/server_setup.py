"""Idempotent Discord server builder (REST, bot token from env DISCORD_BOT_TOKEN). Never deletes anything.
Writes channel ids to tools/channels.json and webhook URLs to a private file (path arg), never printed."""
import json, os, sys, time, urllib.request, urllib.error
API = "https://discord.com/api/v10"; GUILD = "1566899035883970691"; TOK = os.environ["DISCORD_BOT_TOKEN"]
SEND, VIEW, THREADS = 0x800, 0x400, 0x4000000000  # send messages, view, send in threads
LAYOUT = [
  ("📌 START HERE", [("welcome-how-it-works", "Start here: how MONEYHUNTER works, grades, rules", True),
                    ("control-panel", "Click the pinned panel: deals, calculator, price check", True)]),
  ("🔥 LIVE DEALS", [("buy-now", "🟢 A-grade: every check passes. Act fast, verify sold comps", True),
                    ("verify", "🟡 B-grade: numbers work, check comps before buying", True),
                    ("fast-movers", "⚡ A/B deals expected to sell in 10 days or less", True),
                    ("price-errors", "⚡ Possible price errors and very hot deals (may be cancelled)", True),
                    ("trainers", "👟 Trainer and sportswear deals", True), ("lego", "🧱 LEGO deals", True),
                    ("games-consoles", "🎮 Games, consoles, accessories", True), ("tools", "🛠️ Power tool deals", True),
                    ("fragrance", "🧴 Fragrance deals (check for testers/fakes)", True), ("tech", "💻 Tech and headphones deals", True)]),
  ("📊 INTEL", [("price-drops", "📉 Items whose price fell since an earlier scan", True),
               ("trending", "🌡️ Hottest hotukdeals right now", True), ("near-misses", "🟠 Daily 8am digest of deals that nearly passed", True),
               ("seasonal-calendar", "📅 UK flipping calendar: when to buy and sell", True)]),
  ("💸 FLIPPING", [("flip-log", "📒 Log your flips with the button. Earns community XP", True),
                  ("wins", "🏆 Post your wins. Big logged flips are shared here too", False),
                  ("sold-comps", "🧾 Submit real sold prices with the button to improve pricing", True),
                  ("leaderboard", "🥇 Weekly community XP leaderboard (Mondays 9am)", True),
                  ("flip-chat", "💬 Ask questions, share tips, sourcing chat", False)]),
  ("🤖 SYSTEM", [("bot-status", "Scan health and reports every 30 min", True)]),
]
def call(method, path, body=None):
    for _ in range(5):
        req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
              headers={"Authorization": f"Bot {TOK}", "Content-Type": "application/json", "User-Agent": "DiscordBot (moneyhunter, 1)"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                t = r.read(); return json.loads(t) if t else {}
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(float(json.loads(e.read() or b"{}").get("retry_after", 1)) + 0.2); continue
            raise RuntimeError(f"{method} {path} -> {e.code} {e.read()[:200]}")
def main(hook_file):
    chans = call("GET", f"/guilds/{GUILD}/channels"); by = {(c["name"], c.get("parent_id")): c for c in chans}
    cats = {c["name"]: c for c in chans if c["type"] == 4}
    ids, hooks = {}, {}
    me = call("GET", "/users/@me")["id"]
    for pos, (cname, items) in enumerate(LAYOUT):
        cat = cats.get(cname) or call("POST", f"/guilds/{GUILD}/channels", {"name": cname, "type": 4, "position": pos})
        for name, topic, readonly in items:
            ch = by.get((name, cat["id"]))
            ow = [{"id": GUILD, "type": 0, "deny": str(SEND | THREADS), "allow": "0"}, {"id": me, "type": 1, "allow": str(SEND | VIEW), "deny": "0"}] if readonly else []
            if not ch:
                ch = call("POST", f"/guilds/{GUILD}/channels", {"name": name, "type": 0, "topic": topic, "parent_id": cat["id"], "permission_overwrites": ow})
                print("created #" + name)
            else:
                print("exists  #" + name)
            ids[name] = ch["id"]
            if readonly and name not in ("welcome-how-it-works", "control-panel"):
                wh = [w for w in call("GET", f"/channels/{ch['id']}/webhooks") if w.get("application_id") and w.get("token")]
                w = wh[0] if wh else call("POST", f"/channels/{ch['id']}/webhooks", {"name": "MONEYHUNTER"})
                hooks[name] = f"https://discord.com/api/webhooks/{w['id']}/{w['token']}"
    json.dump(ids, open(os.path.join(os.path.dirname(__file__), "channels.json"), "w"), indent=1)
    fd = os.open(hook_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600); os.write(fd, json.dumps(hooks).encode()); os.close(fd)
    print(f"{len(ids)} channels, {len(hooks)} app-owned webhooks (URLs saved privately, not printed)")
if __name__ == "__main__": main(sys.argv[1])
