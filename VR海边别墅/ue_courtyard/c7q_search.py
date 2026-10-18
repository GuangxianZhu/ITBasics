# helper: 在你电脑上查 ambientCG, 把候选材质 ID 写到 c7q.txt (之后选定后填进 c7_pbr.py 的 SURF)
import json, os, sys, urllib.parse, urllib.request
D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
out = []
for q in sys.argv[1:]:
    url = "https://ambientcg.com/api/v2/full_json?type=Material&limit=8&sort=Popular&q=" + urllib.parse.quote(q.replace("_", " "))
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read())
    out.append("%s: %s" % (q, ", ".join("%s(%s)" % (a["assetId"], a.get("displayName", "")) for a in d.get("foundAssets", []))))
open(os.path.join(D, "c7q.txt"), "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out))
