import json
import re
import urllib.request

html = urllib.request.urlopen("https://stevenslatedrums.com/", timeout=30).read().decode("utf-8", "replace")
urls = sorted(set(re.findall(r'https?://[^"\'>\s]+\.(?:mp3|wav|m4a|ogg)', html, re.I)))
print("audio urls", len(urls))
for u in urls[:50]:
    print(u)

# Next.js / JSON blobs
for m in re.finditer(r'\{[^{}]{0,2000}(?:Cutya|Rock|Metal|audio)[^{}]{0,2000}\}', html):
    if "http" in m.group(0):
        print("blob", m.group(0)[:300])

# script src
scripts = re.findall(r'src="([^"]+\.js)"', html)
print("scripts", len(scripts))
for s in scripts[:15]:
    print(s)
