import urllib.request
import urllib.error
import json

key = "AIzaSyCC2hq4sQD4oN230CARbwQWmWJsBxHBuCU"
models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro", "gemini-flash-latest"]
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
