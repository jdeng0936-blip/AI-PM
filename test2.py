import urllib.request
import json
url = 'https://api.github.com/search/issues?q=repo:openclaw/openclaw+gpt5.4'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        if data['items']:
            url2 = data['items'][0]['comments_url']
            req2 = urllib.request.Request(url2, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req2) as resp2:
                comms = json.loads(resp2.read().decode())
                for c in comms:
                    print(c['body'][:500])
        else:
            print("No items found.")
except Exception as e:
    print(e)
