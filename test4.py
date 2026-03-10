import urllib.request
import json
url = 'https://api.github.com/repos/openclaw/openclaw/pulls/36590'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        print(data.get('body', '')[:1000])
except Exception as e:
    print(e)
