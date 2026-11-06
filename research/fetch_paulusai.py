import io, os, sys, tarfile, urllib.request, ssl, time

base = r"C:\Users\asus\Documents\deepseek-harness\default-workspace\Resident\research"
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def get(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 research"})
    with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
        data = r.read()
    with open(dest, "wb") as f:
        f.write(data)
    print(f"OK {len(data)} bytes -> {dest}")

targz = os.path.join(base, "paulusai-master.tar.gz")
if not os.path.exists(targz) or os.path.getsize(targz) < 100000:
    get("https://codeload.github.com/Pavel6625/PaulusAI/tar.gz/refs/heads/master", targz)

out = os.path.join(base, "paulusai-src")
os.makedirs(out, exist_ok=True)

def extract_one(t, m):
    target = os.path.join(out, os.path.relpath(m.name, "PaulusAI-master"))
    if m.isdir():
        os.makedirs(target, exist_ok=True)
        return
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with t.extractfile(m) as src, open(target, "wb") as dst:
        dst.write(src.read())
    print("  wrote", os.path.relpath(target, out).replace("\\", "/"))

with tarfile.open(targz, "r:gz") as t:
    members = t.getmembers()
    deferred = []
    for m in members:
        parts = m.name.replace("\\", "/").split("/")
        if any(p.startswith(".") for p in parts):
            continue
        try:
            extract_one(t, m)
        except Exception as e:
            print("  retry once for", m.name, "->", e)
            deferred.append(m)
    for m in deferred:
        time.sleep(1)
        try:
            extract_one(t, m)
        except Exception as e:
            print("  FAILED", m.name, "->", e)

print("done, files:")
for root, dirs, files in os.walk(out):
    rel = os.path.relpath(root, out)
    for f in files:
        print(os.path.join(rel, f).replace("\\", "/"))

# dotfiles separately via raw.githubusercontent.com
for name in [".env.example", ".gitignore", ".gitattributes"]:
    dest = os.path.join(out, name[1:] + ".txt")
    try:
        get(f"https://raw.githubusercontent.com/Pavel6625/PaulusAI/master/{name}", dest)
    except Exception as e:
        print("raw fetch failed", name, "->", e)
