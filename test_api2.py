import urllib.request, json
req = urllib.request.Request('https://ai-lab-platform.com/api/orchestration/sessions') # wait, the API doesn't have a public URL, it's accessed via frontend proxy.
