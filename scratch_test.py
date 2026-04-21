import urllib.request
import urllib.error
import json

key = "AIzaSyDZRgQy43XOTGsRsR0bj8aZ3sl8gjC370s"
models = ["gemini-1.5-flash-8b", "gemini-1.5-flash-latest", "gemini-1.0-pro"]
results = {}

for m in models:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
    payload = json.dumps({"contents": [{"parts":[{"text": "hi"}]}]}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req)
        results[m] = "200 OK"
    except urllib.error.HTTPError as e:
        results[m] = f"HTTP {e.code}"
    except Exception as e:
        results[m] = str(e)

print(json.dumps(results, indent=2))
