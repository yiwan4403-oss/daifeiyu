# Fetch Crescent Grove repo metadata from GitHub API and save JSON to disk.
import json, os, sys, urllib.request, urllib.error, time

OUT = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "research-script", "Accept": "application/vnd.github+json"}

def get(url, fname, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            path = os.path.join(OUT, fname)
            with open(path, "wb") as f:
                f.write(data)
            print(f"OK {url} -> {fname} ({len(data)} bytes)")
            return
        except urllib.error.HTTPError as e:
            print(f"HTTP {e.code} for {url}")
            if e.code == 403 or e.code == 429:
                time.sleep(5)
                continue
            return
        except Exception as e:
            print(f"ERR {url}: {e}")
            time.sleep(3)
    print(f"FAILED {url}")

get("https://api.github.com/repos/Canon-73/crescent-grove", "repo.json")
get("https://api.github.com/repos/Canon-73/crescent-grove/releases?per_page=20", "releases.json")
get("https://api.github.com/repos/Canon-73/crescent-grove/releases/latest", "release_latest.json")
get("https://api.github.com/repos/Canon-73/crescent-grove/license", "license.json")
get("https://api.github.com/repos/Canon-73/crescent-grove/contents/", "root_contents.json")
get("https://api.github.com/repos/Canon-73/crescent-grove/git/trees/HEAD?recursive=1", "tree.json")
get("https://api.github.com/repos/Canon-73/crescent-grove/commits?per_page=5", "commits.json")
get("https://api.github.com/repos/Canon-73/crescent-grove/contributors", "contributors.json")
get("https://api.github.com/repos/Canon-73/crescent-grove/languages", "languages.json")
get("https://raw.githubusercontent.com/Canon-73/crescent-grove/main/README.md", "README_main.md")
get("https://raw.githubusercontent.com/Canon-73/crescent-grove/master/README.md", "README_master.md")
print("done")
