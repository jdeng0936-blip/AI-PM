import urllib.request
import json
url = 'https://api.github.com/search/issues?q=repo:openclaw/openclaw+gpt5.4'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        if data['items']:
            print(data['items'][0]['body'][:1000])
        else:
            print("No items found.")
except Exception as e:
    print(e)
