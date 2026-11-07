"""Read only the private tier INDEX; never log response bodies or credentials."""
import json
import os
import urllib.request

URL = "https://api.github.com/repos/jwavez/moneyhunter-private/contents/tier.json?ref=data"

def validate(document):
    if not isinstance(document, dict): raise ValueError("tier must be an object")
    value = document.get("tier")
    if type(value) is not int or not 0 <= value <= 4: raise ValueError("tier must be an integer index 0-4")
    return value

def fetch(token, opener=None):
    if not token: return 0, "not configured"
    opener = opener or urllib.request.urlopen
    req = urllib.request.Request(URL, headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github.raw+json"})
    try:
        with opener(req, timeout=10) as response:
            return validate(json.load(response)), ""
    except Exception as exc:
        # Deliberately never echo private body/URL/token or an exception message.
        return 0, type(exc).__name__

def main():
    tier, warning = fetch(os.getenv("MH_PRIVATE_TOKEN", ""))
    print(f"Community index {tier}; " + ("private tier unavailable/invalid; starter fallback" if warning else "typed tier read OK"))
    if warning: print("::warning::Private tier read failed or not configured; using community index 0 (starter)")
    with open(os.environ["GITHUB_ENV"], "a") as out:
        out.write(f"MH_TIER={tier}\nMH_TIER_WARNING={'fallback' if warning else ''}\n")

if __name__ == "__main__": main()
