import urllib.request
import json
url = 'https://api.github.com/search/repositories?q=org:openclaw+gpt-5.4'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        print([x['full_name'] for x in data.get('items', [])])
except Exception as e:
    print(e)
