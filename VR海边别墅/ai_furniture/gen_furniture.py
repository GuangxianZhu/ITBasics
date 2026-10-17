# -*- coding: utf-8 -*-
"""
AI 家具生成: 文字 → Z-Image 出产品图 → Hunyuan3D 2.1 出 3D 形状（.glb）

用 GenImgs 的 Python 运行（生成AI家具.bat 会自动找）:
    python gen_furniture.py                  全部家具（已经有模型的跳过）
    python gen_furniture.py --only sofa,plant   只做这几件（会覆盖旧的）
    python gen_furniture.py --redo           全部重做
    python gen_furniture.py --images-only    只出图，先看看图满不满意
    python gen_furniture.py --3d-only        用现有图片只做 3D

想用自己的图（比如从房产照片里截的沙发）: 放到 my_images/<名字>.png（名字同 furniture.json 里的 name），
会优先用它而不是 AI 出图。图片背景越干净越好（白底最好）。

原理和取舍:
  - 用的是 ComfyUI 自带的 Hunyuan3D 节点（不装插件、不编译），只生成"形状"。
    官方的贴图生成要编译 CUDA 扩展，现成的预编译包是 CUDA 12.6 的，RTX 5090 需要 12.8+，所以先不做；
    颜色和质感由 furniture.json 里的 material 决定，Blender 导入时上材质。
  - 两个阶段分开跑（先全部出图，释放显存，再全部做 3D），避免 Z-Image 和 Hunyuan3D 同时占显存。
"""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
IMAGES = HERE / "images"          # AI 出的图
MY_IMAGES = HERE / "my_images"    # 你自己放的图（优先）
MODELS = HERE / "models"          # 输出的 .glb（Blender 构建时读取）
CKPT_NAME = "hunyuan_3d_v2.1.safetensors"


def find_genimgs() -> Path:
    cands = []
    if os.environ.get("GENIMGS"):
        cands.append(Path(os.environ["GENIMGS"]))
    p = HERE / "genimgs_path.txt"
    if p.exists():
        cands.append(Path(p.read_text(encoding="utf-8").strip()))
    repo_root = HERE.parents[1]                       # .../ITBasics
    cands += [repo_root.parent / "GenImgs", Path(r"C:\work\GenImgs")]
    for c in cands:
        if (c / "gen.py").exists() and (c / "ComfyUI").exists():
            return c
    raise SystemExit("找不到 GenImgs（需要里面有 gen.py 和 ComfyUI）。把路径写进 ai_furniture/genimgs_path.txt")


def graph_3d(image_name: str, seed: int, prefix: str, steps: int, octree: int) -> dict:
    """ComfyUI 官方模板 3d_hunyuan3d-v2.1.json 的节点图（API 格式）"""
    return {
        "1": {"class_type": "ImageOnlyCheckpointLoader", "inputs": {"ckpt_name": CKPT_NAME}},
        "2": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "3": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 1.0}},
        "13": {"class_type": "CLIPVisionEncode", "inputs": {"clip_vision": ["1", 1], "image": ["2", 0], "crop": "center"}},
        "6": {"class_type": "Hunyuan3Dv2Conditioning", "inputs": {"clip_vision_output": ["13", 0]}},
        "4": {"class_type": "EmptyLatentHunyuan3Dv2", "inputs": {"resolution": 4096, "batch_size": 1}},
        "7": {"class_type": "KSampler", "inputs": {"model": ["3", 0], "positive": ["6", 0], "negative": ["6", 1],
              "latent_image": ["4", 0], "seed": seed, "steps": steps, "cfg": 5.0,
              "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0}},
        "8": {"class_type": "VAEDecodeHunyuan3D", "inputs": {"samples": ["7", 0], "vae": ["1", 2],
              "num_chunks": 8000, "octree_resolution": octree}},
        "9": {"class_type": "VoxelToMesh", "inputs": {"voxel": ["8", 0], "algorithm": "surface net", "threshold": 0.6}},
        "10": {"class_type": "SaveGLB", "inputs": {"mesh": ["9", 0], "filename_prefix": prefix}},
    }


def wait_outputs(gen, pid: str, timeout: float = 1800.0) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = gen.http(f"/history/{pid}")
        if pid in h:
            item = h[pid]
            st = item.get("status", {})
            if st.get("status_str") == "error":
                msgs = [m for m in st.get("messages", []) if m[0] == "execution_error"]
                raise RuntimeError(msgs[0][1].get("exception_message", "error").strip() if msgs else "ComfyUI error")
            return item.get("outputs", {})
        time.sleep(1.0)
    raise TimeoutError("等待 ComfyUI 超时")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="逗号分隔的名字")
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--images-only", action="store_true")
    ap.add_argument("--3d-only", dest="only3d", action="store_true")
    ap.add_argument("--steps", type=int, default=30, help="Hunyuan3D 采样步数")
    ap.add_argument("--octree", type=int, default=256, help="网格精度 256/384/512（越高越细越慢）")
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()

    cfg = json.loads((HERE / "furniture.json").read_text(encoding="utf-8"))
    items = cfg["items"]
    if a.only:
        want = [s.strip() for s in a.only.split(",") if s.strip()]
        unknown = [w for w in want if w not in {i["name"] for i in items}]
        if unknown:
            raise SystemExit(f"furniture.json 里没有: {unknown}")
        items = [i for i in items if i["name"] in want]
    force = a.redo or bool(a.only)
    todo = [i for i in items if force or not (MODELS / f"{i['name']}.glb").exists()]
    if not todo:
        print("全部家具都已经有模型了（要重做用 --redo 或 --only 名字）")
        return

    genimgs = find_genimgs()
    sys.path.insert(0, str(genimgs))
    import gen  # GenImgs/gen.py: 启动/连接 ComfyUI、出图
    ckpt = genimgs / "ComfyUI" / "models" / "checkpoints" / CKPT_NAME
    if not a.images_only and not ckpt.exists():
        raise SystemExit(f"缺少模型 {ckpt}（运行 生成AI家具.bat 会自动下载）")
    for d in (IMAGES, MY_IMAGES, MODELS):
        d.mkdir(exist_ok=True)
    gen.ensure_server()
    seed = a.seed if a.seed is not None else int(time.time()) % 100000
    log = []

    # ---------------- 阶段 1: 出图
    if not a.only3d:
        need = [i for i in todo if not any((MY_IMAGES / f"{i['name']}{e}").exists() for e in (".png", ".jpg", ".jpeg", ".webp"))]
        if need:
            batch = [dict(prompt=f"{i['prompt']}, {cfg['style']}", name=f"furn_{i['name']}", label=i["name"], seed=seed + k)
                     for k, i in enumerate(need)]
            print(f"[1/2] Z-Image 出图 {len(batch)} 张 ...", flush=True)
            summary, meta = gen.run_batch("z", batch, run_name="furniture", raw=True)
            print("     ", summary, flush=True)
            for f in meta["files"]:
                f = Path(f)
                name = f.stem.replace("furn_", "", 1)
                shutil.copy(f, IMAGES / f"{name}.png")
            if meta.get("sheet"):
                shutil.copy(meta["sheet"], HERE / "images_sheet.jpg")
                print("      图片总览: ai_furniture\\images_sheet.jpg", flush=True)
    if a.images_only:
        print("只出图，完成。满意的话运行 --3d-only；不满意的用 --only 名字 重出。")
        return

    # ---------------- 阶段 2: 3D
    try:
        gen.http("/free", {"unload_models": True, "free_memory": True})     # 释放 Z-Image 占的显存
    except Exception:
        pass
    in_dir = genimgs / "ComfyUI" / "input"
    in_dir.mkdir(exist_ok=True)
    print(f"[2/2] Hunyuan3D 2.1 生成 {len(todo)} 个模型（每个约 1 分钟，第一次要加载模型）...", flush=True)
    for k, it in enumerate(todo):
        name = it["name"]
        src = next((MY_IMAGES / f"{name}{e}" for e in (".png", ".jpg", ".jpeg", ".webp")
                    if (MY_IMAGES / f"{name}{e}").exists()), IMAGES / f"{name}.png")
        if not src.exists():
            log.append(f"{name}: 没有图片，跳过")
            print("     ", log[-1], flush=True)
            continue
        dst_in = in_dir / f"furn_{name}{src.suffix}"
        shutil.copy(src, dst_in)
        t0 = time.time()
        try:
            g = graph_3d(dst_in.name, seed + 100 + k, f"furniture3d/{name}", a.steps, a.octree)
            pid = gen.http("/prompt", {"prompt": g, "client_id": "furniture"})["prompt_id"]
            outs = wait_outputs(gen, pid)
            glbs = [f for o in outs.values() for lst in o.values() if isinstance(lst, list)
                    for f in lst if isinstance(f, dict) and str(f.get("filename", "")).endswith(".glb")]
            if not glbs:
                raise RuntimeError("ComfyUI 没有返回 .glb")
            f = glbs[0]
            path = gen.OUT / f.get("subfolder", "") / f["filename"]
            shutil.copy(path, MODELS / f"{name}.glb")
            mb = (MODELS / f"{name}.glb").stat().st_size / 1e6
            log.append(f"{name}: OK {time.time() - t0:.0f}s  {mb:.1f}MB  (图: {src.name})")
        except Exception as e:
            log.append(f"{name}: 失败 {e}")
        print("     ", log[-1], flush=True)
    (HERE / "report.txt").write_text("\n".join(log), encoding="utf-8")
    ok = sum(1 for l in log if ": OK" in l)
    print(f"完成 {ok}/{len(todo)}。模型在 ai_furniture\\models\\，下次运行 启动_Godot版.bat 会自动换上。")


if __name__ == "__main__":
    main()
