"""Discord webhook poster. Reads MONEYHUNTER_DISCORD_WEBHOOK; never prints it.
If unset or dry_run=True, prints the embed JSON instead."""
import json, os, time, urllib.request, urllib.error

ENV = "MONEYHUNTER_DISCORD_WEBHOOK"
COLORS = {"A": 0x2ECC71, "B": 0xF1C40F, "R": 0xE74C3C, "T": 0x3498DB}

def post(embeds: list, content: str = "", dry_run: bool = False, components: list = None) -> int:
    url = os.getenv(ENV)
    payload = {"username": "MONEYHUNTER", "content": content, "embeds": embeds[:10]}
    if os.getenv("MONEYHUNTER_AVATAR_URL"):
        payload["avatar_url"] = os.environ["MONEYHUNTER_AVATAR_URL"]
    if components:
        payload["components"] = components   # link buttons only (non-app webhook)
        url = url and url + ("&" if "?" in url else "?") + "with_components=true"
    if dry_run or not url:
        print(f"[discord] DRY RUN ({'no webhook set' if not url else 'dry-run flag'}): {len(embeds)} embed(s)")
        print(json.dumps(payload, indent=2, ensure_ascii=False)[:4000])
        return 0
    data = json.dumps(payload).encode()
    for _ in range(3):
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "moneyhunter/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status
        except urllib.error.HTTPError as e:
            if e.code == 429:   # Discord rate limit: 30 msgs/min per webhook [S]
                time.sleep(float(json.loads(e.read() or b"{}").get("retry_after", 2)))
                continue
            print(f"[discord] HTTP {e.code}")
            return e.code
    return 429
