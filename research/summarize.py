# Summarize fetched JSON files into readable text.
import json, os

OUT = os.path.dirname(os.path.abspath(__file__))

def load(name):
    with open(os.path.join(OUT, name), "r", encoding="utf-8") as f:
        return json.load(f)

lines = []

repo = load("repo.json")
lines.append("=== REPO ===")
for k in ["full_name", "description", "homepage", "default_branch", "created_at",
          "updated_at", "pushed_at", "stargazers_count", "forks_count",
          "open_issues_count", "watchers_count", "subscribers_count", "size",
          "archived", "has_wiki", "has_pages", "license", "topics", "language",
          "fork", "mirror_url", "allow_forking", "visibility"]:
    lines.append(f"{k}: {json.dumps(repo.get(k), ensure_ascii=False)}")

lines.append("\n=== COMMITS ===")
for c in load("commits.json"):
    lines.append(f"{c['sha'][:10]} | {c['commit']['author']['date']} | {c['commit']['message']!r} | gh_login={c.get('author') and c['author'].get('login')} | commit_author={c['commit']['author']['name']}")

lines.append("\n=== LATEST RELEASE ===")
rl = load("release_latest.json")
if rl:
    for k in ["tag_name", "name", "published_at", "created_at", "draft", "prerelease", "target_commitish"]:
        lines.append(f"{k}: {json.dumps(rl.get(k), ensure_ascii=False)}")
    lines.append(f"body: {str(rl.get('body'))[:2000]}")
    for a in rl.get("assets", []):
        lines.append(f"asset: {a['name']} size={a['size']} dl={a['download_count']} url={a['browser_download_url']}")

lines.append("\n=== ALL RELEASES ===")
rels = load("releases.json")
for r in rels:
    lines.append(f"- {r['tag_name']} | published={r['published_at']} | prerelease={r['prerelease']} | draft={r['draft']} | name={r['name']!r}")
    for a in r.get("assets", []):
        lines.append(f"    asset: {a['name']} size={a['size']} dl={a['download_count']}")

lines.append("\n=== LICENSE ===")
lic = load("license.json")
lines.append(json.dumps(lic, ensure_ascii=False, indent=2)[:2000])

lines.append("\n=== LANGUAGES ===")
lines.append(json.dumps(load("languages.json"), indent=2))

lines.append("\n=== ROOT CONTENTS ===")
for e in load("root_contents.json"):
    lines.append(f"{e['type']:5} {e['size']:>10} {e['name']}")

lines.append("\n=== TREE (path, type, size) ===")
tree = load("tree.json")
for e in tree.get("tree", []):
    lines.append(f"{e['type']:5} {e.get('size', 0):>10} {e['path']}")

with open(os.path.join(OUT, "summary.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"wrote {len(lines)} lines")
