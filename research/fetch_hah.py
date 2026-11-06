import json, os, sys, urllib.request

BASE = r"C:\Users\asus\Documents\deepseek-harness\default-workspace\Resident\research"
os.makedirs(BASE, exist_ok=True)

def get(url, path, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "research-script", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    with open(os.path.join(BASE, path), "wb") as f:
        f.write(data)
    print(f"OK {url} -> {path} ({len(data)} bytes)")
    return data

# 1. tarball
tarball = None
for branch in ("main", "master"):
    url = f"https://codeload.github.com/ericwang915/HerAndHim/tar.gz/refs/heads/{branch}"
    try:
        tarball = get(url, f"herandhim-{branch}.tar.gz")
        print("BRANCH:", branch)
        break
    except Exception as e:
        print("branch fail", branch, e)

# 2. API metadata
for name, url in [
    ("api_repo.json", "https://api.github.com/repos/ericwang915/HerAndHim"),
    ("api_commits.json", "https://api.github.com/repos/ericwang915/HerAndHim/commits?per_page=5"),
    ("api_releases.json", "https://api.github.com/repos/ericwang915/HerAndHim/releases?per_page=10"),
    ("api_tags.json", "https://api.github.com/repos/ericwang915/HerAndHim/tags?per_page=20"),
    ("api_license.json", "https://api.github.com/repos/ericwang915/HerAndHim/license"),
    ("api_languages.json", "https://api.github.com/repos/ericwang915/HerAndHim/languages"),
    ("api_contents_root.json", "https://api.github.com/repos/ericwang915/HerAndHim/contents/"),
]:
    try:
        get(url, name)
    except Exception as e:
        print("FAIL", url, e)
print("DONE")
