#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pypdf>=4.0", "httpx>=0.27"]
# ///
"""处理超过 MinerU 单次限制 (200MB / 600 页) 的大 PDF：
下载（可选） → 拆分（页数 + 大小双约束，含 overlap）→ batch 上传 MinerU
→ 轮询 → 下载 zip 结果 → 合并 full.md。

示例：
    ./mineru_large_pdf.py \\
        --input 'https://47.102.36.175/share/mineru-upload/foo.pdf' \\
        --out-dir mineru_output/foo \\
        --pages-per-part 500 --overlap 5
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import ssl
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx
from pypdf import PdfReader, PdfWriter

MINERU_API = "https://mineru.net/api/v4"
MAX_SIZE_MB = 190  # 留余量，MinerU 限制 200MB
MAX_PAGES = 590    # 留余量，MinerU 限制 600 页


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def slugify(name: str) -> str:
    name = re.sub(r"\.pdf$", "", name, flags=re.I)
    name = re.sub(r"[\s/\\:*?\"<>|]+", "_", name)
    return name[:120].strip("_")


def fetch_pdf(src: str, dst: Path) -> Path:
    """若 src 是 URL 则下载到 dst；若是本地路径直接返回。"""
    if src.startswith(("http://", "https://")):
        log(f"下载 {src} → {dst}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        # 自签证书兜底
        with httpx.stream("GET", src, verify=False, timeout=None, follow_redirects=True) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            done = 0
            last_log = 0
            with dst.open("wb") as f:
                for chunk in r.iter_bytes(1024 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    if total and done - last_log > total / 20:
                        log(f"  {done/1e6:.1f}/{total/1e6:.1f} MB ({done*100/total:.0f}%)")
                        last_log = done
        return dst
    p = Path(src).expanduser().resolve()
    if not p.exists():
        sys.exit(f"找不到文件: {p}")
    return p


@dataclass
class Part:
    idx: int
    start: int  # 1-based, inclusive
    end: int    # 1-based, inclusive
    pdf_path: Path


def plan_parts(total_pages: int, pages_per_part: int, overlap: int) -> list[tuple[int, int]]:
    """返回 [(start, end), ...]（1-based inclusive），主体 pages_per_part 页 + 末尾 overlap 页。
    相邻卷的 overlap 区是前卷末尾的 overlap 页与后卷开头的 overlap 页重复。
    实际实现：每卷起点 step = pages_per_part，长度 = pages_per_part + overlap（最后一卷不加 overlap）。
    """
    assert pages_per_part + overlap <= MAX_PAGES, "pages_per_part + overlap 超 MinerU 单次页数上限"
    parts = []
    start = 1
    step = pages_per_part
    while start <= total_pages:
        end = min(start + step + overlap - 1, total_pages)
        parts.append((start, end))
        if end >= total_pages:
            break
        start += step
    return parts


def split_pdf(
    src_pdf: Path,
    out_dir: Path,
    pages_per_part: int,
    overlap: int,
) -> list[Part]:
    reader = PdfReader(str(src_pdf))
    total = len(reader.pages)
    log(f"PDF 总页数: {total}")

    # 若单卷大小超限，自适应减小 pages_per_part
    while True:
        ranges = plan_parts(total, pages_per_part, overlap)
        log(f"计划拆分 {len(ranges)} 卷（主体 {pages_per_part} + overlap {overlap}）")
        parts: list[Part] = []
        for i, (s, e) in enumerate(ranges, 1):
            part_path = out_dir / f"part{i:02d}_p{s:04d}-{e:04d}.pdf"
            writer = PdfWriter()
            for p in range(s - 1, e):
                writer.add_page(reader.pages[p])
            part_path.parent.mkdir(parents=True, exist_ok=True)
            with part_path.open("wb") as f:
                writer.write(f)
            size_mb = part_path.stat().st_size / 1e6
            log(f"  part{i:02d}: 页 {s}-{e}（{e-s+1}页）{size_mb:.1f} MB → {part_path.name}")
            parts.append(Part(idx=i, start=s, end=e, pdf_path=part_path))
            if size_mb > MAX_SIZE_MB:
                log(f"  ⚠ 超过 {MAX_SIZE_MB}MB，缩小页数重试")
                for pp in parts:
                    pp.pdf_path.unlink(missing_ok=True)
                pages_per_part = max(50, int(pages_per_part * MAX_SIZE_MB / size_mb) - 10)
                break
        else:
            return parts


def mineru_batch_upload(parts: list[Part], token: str, language: str = "ch") -> str:
    """用 batch 接口拿上传 URL，依次 PUT 上传。返回 batch_id。"""
    files = [{"name": p.pdf_path.name, "is_ocr": True} for p in parts]
    body = {
        "files": files,
        "model_version": "vlm",
        "language": language,
        "enable_formula": True,
        "enable_table": True,
    }
    log(f"申请 batch 上传地址（{len(files)} 个文件）")
    with httpx.Client(timeout=60) as cli:
        r = cli.post(
            f"{MINERU_API}/file-urls/batch",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        r.raise_for_status()
        data = r.json()
    if data.get("code") != 0:
        sys.exit(f"申请失败: {data}")
    batch_id = data["data"]["batch_id"]
    file_urls = data["data"]["file_urls"]
    log(f"batch_id: {batch_id}")

    for p, url in zip(parts, file_urls):
        size_mb = p.pdf_path.stat().st_size / 1e6
        log(f"  上传 part{p.idx:02d} ({size_mb:.1f} MB) → OSS")
        with p.pdf_path.open("rb") as f:
            # OSS 要求空 Content-Type
            resp = httpx.put(url, content=f, headers={"Content-Type": ""}, timeout=None)
            resp.raise_for_status()
    return batch_id


def mineru_wait_batch(batch_id: str, token: str, poll_sec: int = 30) -> list[dict]:
    """轮询直到所有任务 done/failed。返回每个文件的 extract_result 项。"""
    url = f"{MINERU_API}/extract-results/batch/{batch_id}"
    last_states: dict[str, str] = {}
    while True:
        try:
            with httpx.Client(timeout=30) as cli:
                r = cli.get(url, headers={"Authorization": f"Bearer {token}"})
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            log(f"  轮询异常，忽略: {e}")
            time.sleep(poll_sec)
            continue
        results = data.get("data", {}).get("extract_result", [])
        states = {r["file_name"]: r.get("state", "?") for r in results}
        if states != last_states:
            summary = ", ".join(f"{n.split('_',1)[0]}={s}" for n, s in states.items())
            log(f"状态: {summary}")
            last_states = states
        pending = [r for r in results if r.get("state") not in ("done", "failed")]
        if not pending:
            return results
        time.sleep(poll_sec)


def download_and_extract(results: list[dict], parts: list[Part], out_dir: Path) -> list[Path]:
    """下载每个 part 的 full_zip 并解压到 out_dir/<part-name>/。返回各 part 的 full.md 路径。"""
    by_name = {r["file_name"]: r for r in results}
    md_paths: list[Path] = []
    for p in parts:
        entry = by_name.get(p.pdf_path.name)
        if not entry or entry.get("state") != "done":
            log(f"  part{p.idx:02d} 未 done: {entry}")
            continue
        zip_url = entry.get("full_zip_url")
        if not zip_url:
            log(f"  part{p.idx:02d} 无 full_zip_url")
            continue
        part_dir = out_dir / f"part{p.idx:02d}"
        part_dir.mkdir(parents=True, exist_ok=True)
        log(f"  下载 part{p.idx:02d} zip")
        zb = httpx.get(zip_url, timeout=None).content
        with zipfile.ZipFile(io.BytesIO(zb)) as zf:
            zf.extractall(part_dir)
        md = part_dir / "full.md"
        if md.exists():
            md_paths.append(md)
        else:
            log(f"  ⚠ 未找到 full.md in {part_dir}")
    return md_paths


def merge_full_md(md_paths: list[Path], parts: list[Part], out_path: Path) -> None:
    """直接拼接 + 分卷标记。"""
    lines: list[str] = []
    for p, md in zip(parts, md_paths):
        lines.append(f"\n\n<!-- === part {p.idx:02d} (pages {p.start}-{p.end}) === -->\n\n")
        lines.append(md.read_text(encoding="utf-8"))
    out_path.write_text("".join(lines), encoding="utf-8")
    log(f"合并完成 → {out_path} ({out_path.stat().st_size/1e6:.2f} MB)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="PDF URL 或本地路径")
    ap.add_argument("--out-dir", required=True, help="输出根目录（存放 part PDF + 解压结果 + 合并 md）")
    ap.add_argument("--pages-per-part", type=int, default=500)
    ap.add_argument("--overlap", type=int, default=5)
    ap.add_argument("--language", default="ch")
    ap.add_argument("--token", default=os.environ.get("MINERU_TOKEN", ""), help="默认读 $MINERU_TOKEN")
    ap.add_argument("--skip-download", action="store_true", help="如 --input 已是本地文件，跳过下载")
    ap.add_argument("--skip-split", action="store_true", help="out-dir 下已有 part*.pdf 时跳过拆分")
    ap.add_argument("--resume-batch", default="", help="复用已存在的 batch_id（跳过上传）")
    args = ap.parse_args()

    if not args.token:
        sys.exit("未设置 MINERU_TOKEN")

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    parts_dir = out_dir / "parts"
    parts_dir.mkdir(exist_ok=True)

    # 1. 准备原 PDF
    if args.skip_download and not args.input.startswith(("http://", "https://")):
        src_pdf = Path(args.input).resolve()
    else:
        name = unquote(Path(urlsplit(args.input).path).name) if args.input.startswith(("http://", "https://")) else Path(args.input).name
        src_pdf = out_dir / "source.pdf"
        if not src_pdf.exists():
            fetch_pdf(args.input, src_pdf)
        else:
            log(f"已存在 {src_pdf}，跳过下载")

    # 2. 拆分
    existing = sorted(parts_dir.glob("part*.pdf"))
    if args.skip_split and existing:
        log(f"复用已有 {len(existing)} 个分卷")
        reader = PdfReader(str(src_pdf))
        parts = []
        for i, pth in enumerate(existing, 1):
            m = re.search(r"p(\d+)-(\d+)", pth.name)
            s, e = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
            parts.append(Part(idx=i, start=s, end=e, pdf_path=pth))
    else:
        for f in existing:
            f.unlink()
        parts = split_pdf(src_pdf, parts_dir, args.pages_per_part, args.overlap)

    # 3. 上传 + 轮询
    if args.resume_batch:
        batch_id = args.resume_batch
        log(f"复用 batch_id: {batch_id}")
    else:
        batch_id = mineru_batch_upload(parts, args.token, args.language)
        (out_dir / "batch_id.txt").write_text(batch_id)

    results = mineru_wait_batch(batch_id, args.token)
    (out_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))

    # 4. 下载 + 合并
    md_paths = download_and_extract(results, parts, out_dir)
    if len(md_paths) == len(parts):
        merge_full_md(md_paths, parts, out_dir / "full.md")
    else:
        log(f"⚠ 只成功 {len(md_paths)}/{len(parts)} 卷，未合并")


if __name__ == "__main__":
    main()
