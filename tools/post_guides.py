"""One-off: post + pin a 'Where to sell' guide in each category channel, and a FAST/where-to-sell note in
#fast-movers and #price-drops. Bot token from env DISCORD_BOT_TOKEN (never printed). Skips channels already pinned
with a guide (EDIT=1 edits it instead). Run: DISCORD_BOT_TOKEN=... python3 tools/post_guides.py"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from moneyhunter import sell as S
from moneyhunter.hub import CAT_LABEL
import server_setup as SS
CH = json.load(open(os.path.join(os.path.dirname(__file__), "channels.json")))
CATS = {"trainers": "trainers", "lego": "lego", "games-consoles": "gaming", "tools": "tools", "fragrance": "fragrance", "tech": "tech"}
EXTRA = {
  "fast-movers": {"title": "⚡ Fast movers", "color": 0xF59E0B, "description":
      "Copies of 🟢 BUY and 🟡 VERIFY deals expected to sell in **10 days or less**.\n"
      "No days-to-sell data yet? Trainers and games still count as everyday movers.\n"
      f"⏱️ {S.HOLD_TIP}. Each card shows where to sell first, the backup and the floor exit."},
  "price-drops": {"title": "📉 How price drops work", "color": 0x06B6D4, "description":
      "MONEYHUNTER remembers each deal's price for 45 days. When the same item comes back **10%+ cheaper**, it posts here.\n"
      "This channel fills after a few days of price history. Quiet here means no qualifying drops yet, not a broken bot.\n"
      "#bot-status shows how many drops each hourly scan found."},
}
def pinned_title(cid, me):
    for m in SS.call("GET", f"/channels/{cid}/pins") or []:
        if m.get("author", {}).get("id") == me:
            for e in m.get("embeds", []):
                yield m["id"], e.get("title", "")
def post_pin(name, emb, me):
    cid = CH.get(name)
    if not cid: print(f"#{name}: no channel id, run server_setup first"); return
    mine = [(mid, t) for mid, t in pinned_title(cid, me) if t == emb["title"]]
    if mine:
        if os.getenv("EDIT") == "1": SS.call("PATCH", f"/channels/{cid}/messages/{mine[0][0]}", {"embeds": [emb]}); print(f"#{name}: edited")
        else: print(f"#{name}: already pinned")
        return
    m = SS.call("POST", f"/channels/{cid}/messages", {"embeds": [emb], "allowed_mentions": {"parse": []}})
    SS.call("PUT", f"/channels/{cid}/pins/{m['id']}"); print(f"#{name}: posted + pinned")
def main():
    me = SS.call("GET", "/users/@me")["id"]
    for ch, cat in CATS.items():
        e = S.guide_embed(cat, CAT_LABEL[cat])
        if cat == "trainers": e["description"] = "👟 Trainers and 👕 sportswear\n" + e["description"]
        post_pin(ch, e, me)
    for ch, e in EXTRA.items(): post_pin(ch, e, me)
if __name__ == "__main__": main()
