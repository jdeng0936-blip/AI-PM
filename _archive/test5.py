import urllib.request
import json
url = 'https://api.github.com/search/code?q=repo:openclaw/openclaw+gpt-5.4'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        for item in data.get('items', [])[:5]:
            print(item['html_url'])
except Exception as e:
    print(e)
