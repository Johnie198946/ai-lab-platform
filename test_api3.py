import urllib.request, json
req = urllib.request.Request('http://localhost:8000/api/orchestration/sessions', data=json.dumps({'goal':'你是谁'}).encode('utf-8'), headers={'Content-Type':'application/json'})
try:
    print(urllib.request.urlopen(req).read().decode('utf-8'))
except Exception as e:
    print(e)
