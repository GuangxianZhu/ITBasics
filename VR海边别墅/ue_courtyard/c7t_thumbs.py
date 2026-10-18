# helper: 下载候选材质的缩略图到 court/thumbs/ (只给我挑材质用)
import json, os, sys, urllib.request
D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court", "thumbs")
os.makedirs(D, exist_ok=True)
ids = sys.argv[1:]
url = "https://ambientcg.com/api/v2/full_json?type=Material&include=imageData&id=" + ",".join(ids)
d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read())
got = []
for a in d.get("foundAssets", []):
    pi = a.get("previewImage", {})
    link = pi.get("256-JPG-242424") or pi.get("256-PNG") or (list(pi.values())[0] if pi else None)
    if link:
        open(os.path.join(D, a["assetId"] + ".jpg"), "wb").write(urllib.request.urlopen(urllib.request.Request(link, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read())
        got.append(a["assetId"])
print("thumbs:", got)
