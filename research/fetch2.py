# Fetch key source files from raw.githubusercontent.com into src/.
import os, urllib.request, time

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
os.makedirs(OUT, exist_ok=True)
BASE = "https://raw.githubusercontent.com/Canon-73/crescent-grove/main/"

FILES = [
    "ARCHITECTURE.md",
    "DEVELOPER.md",
    "DISTRIBUTION.md",
    "config.yaml",
    "config.example.yaml",
    "requirements.txt",
    "server.py",
    "core/agent.py",
    "core/scheduler.py",
    "core/context.py",
    "core/compressor.py",
    "core/rag.py",
    "core/wyrd_network.py",
    "core/summary_v2.py",
    "core/llm.py",
    "core/tools.py",
    "core/startup.py",
    "core/app_state.py",
    "core/bootstrap.py",
    "core/ear.py",
    "memory/manager.py",
    "vital/vital_manager.py",
    "vital/desire_manager.py",
    "vital/moodphase.py",
    "vital/moontide_v2.py",
    "programs/README.md",
    "programs/hello_world/main.py",
    "programs/hello_world/manifest.yaml",
    "programs/hello_world/README.md",
    "liner/package.json",
    "dist_template/workspace/IDENTITY.md",
    "dist_template/workspace/SOUL.md",
    "dist_template/workspace/MEMORY.md",
    "dist_template/workspace/USER.md",
    "dist_template/workspace/FILES.md",
    "config/desire_config.json",
    "config/vital_config.json",
    "config/wyrd_config.json",
    "config/moonbeat_config.json",
    "config/moontide_v2_config.json",
    "dist_template/system_prompt/TOP_PROMPT.md",
    "dist_template/system_prompt/salia.md",
]

def fetch(path):
    local = os.path.join(OUT, path.replace("/", "__"))
    if os.path.exists(local) and os.path.getsize(local) > 0:
        print(f"skip {path}")
        return
    url = BASE + path
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "research"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            with open(local, "wb") as f:
                f.write(data)
            print(f"OK   {path} ({len(data)} bytes)")
            return
        except Exception as e:
            print(f"ERR  {path}: {e}")
            time.sleep(3)
    print(f"FAIL {path}")

for p in FILES:
    fetch(p)
print("done")
