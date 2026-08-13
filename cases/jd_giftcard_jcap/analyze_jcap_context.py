import urllib.request
import re

with open("jcap_ujb96b.js", "r", encoding="utf-8") as f:
    content = f.read()

print("\n--- Searching for tk:k ---")
matches = re.finditer(r'.{0,150}tk:k.{0,150}', content)
count = 0
for m in matches:
    print(f"Match {count}:\n{m.group(0)}\n")
    count += 1
    if count > 5:
        break
