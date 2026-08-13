import urllib.request
import re

url = "https://storage.360buyimg.com/jsresource/jcap/version/v2.8.5/1/jcap_ujb96b.js"
print(f"Downloading {url}...")
resp = urllib.request.urlopen(url)
content = resp.read().decode('utf-8')

print(f"Downloaded {len(content)} characters.")

# Save for reference
with open("jcap_ujb96b.js", "w", encoding="utf-8") as f:
    f.write(content)

print("Saved to jcap_ujb96b.js")

# Try to find "tk" and "si"
print("\n--- Searching for 'tk' ---")
matches = re.finditer(r'.{0,50}tk.{0,50}', content)
count = 0
for m in matches:
    print(f"Match {count}: {m.group(0)}")
    count += 1
    if count > 20:
        break
print("\n--- Searching for 'check' ---")
matches = re.finditer(r'.{0,50}check.{0,50}', content)
count = 0
for m in matches:
    print(f"Match {count}: {m.group(0)}")
    count += 1
    if count > 20:
        break
