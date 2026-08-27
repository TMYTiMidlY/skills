#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pypdf>=4.0", "httpx>=0.27", "cryptography>=3.1"]
# ///
"""处理超过 MinerU 当前单次限制 (200MB / 200 页) 的大 PDF：
下载（可选） → 拆分（页数 + 大小双约束，含 overlap）→ batch 上传 MinerU
→ 轮询 → 下载各 part 的原始 zip → 生成带分卷标记的 full.concat.md。

注意：本脚本目前只做原始结果暂存与 Markdown 机械拼接；不合并 JSON / images，
不删除 overlap，也不产出最终 full.md。最终交付必须再经过结构化合并和 agent 接缝复核。

过去 URL 单任务曾按 600 页上限设计，旧默认值是 500；当前官方限制已经统一为
200 页，因此默认使用 198 页主体 + 2 页 overlap，保证每卷总页数不超过 200。

示例：
    ./mineru_large_pdf.py \\
        --input 'https://47.102.36.175/share/mineru-upload/foo.pdf' \\
        --work-dir mineru_work/foo \\
        --pages-per-part 198 --overlap 2
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
MAX_PAGES = 200    # 当前官方精准解析单文件上限 200 页


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def slugify(name: str) -> str:
    name = re.sub(r"\.pdf$", "", name, flags=re.I)
    name = re.sub(r"[\s/\\:*?\"<>|]+", "_", name)
    return name[:120].strip("_")


def wait_until_stable(p: Path, interval: float = 1.5, checks: int = 2, timeout: float = 120.0) -> None:
    """等待本地文件大小稳定，避免读到正在上传/rsync 中的半截 PDF。
    连续 checks 次采样间隔 interval 秒大小一致，才认为传完。
    """
    if not p.exists():
        sys.exit(f"找不到文件: {p}")
    last = -1
    stable = 0
    waited = 0.0
    while True:
        cur = p.stat().st_size
        if cur == last and cur > 0:
            stable += 1
            if stable >= checks:
                return
        else:
            if last != -1:
                log(f"  文件仍在写入: {last/1e6:.1f} → {cur/1e6:.1f} MB，等待稳定…")
            stable = 0
            last = cur
        if waited >= timeout:
            log(f"  文件大小 {timeout}s 内未稳定，放弃等待，按当前内容处理")
            return
        time.sleep(interval)
        waited += interval


def fetch_pdf(src: str, dst: Path, verify_ssl: bool = True) -> Path:
    """若 src 是 URL 则下载到 dst；若是本地路径直接返回（并等待大小稳定）。"""
    if src.startswith(("http://", "https://")):
        log(f"下载 {src} → {dst}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", src, verify=verify_ssl, timeout=None, follow_redirects=True) as r:
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
    wait_until_stable(p)
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
    parts_dir: Path,
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
            part_path = parts_dir / f"part{i:02d}_p{s:04d}-{e:04d}.pdf"
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


def write_parts_manifest(
    src_pdf: Path,
    parts: list[Part],
    work_dir: Path,
    configured_body_pages: int,
    overlap: int,
) -> Path:
    """记录原 PDF 全局页范围与基线保留范围，供结构化 merger 和 agent 接缝复核。"""
    if not parts:
        raise ValueError("没有可写入 manifest 的分卷")
    effective_body_pages = (
        parts[1].start - parts[0].start
        if len(parts) > 1
        else min(configured_body_pages, parts[0].end - parts[0].start + 1)
    )
    rows = []
    for p in parts:
        local_pages = p.end - p.start + 1
        drop_prefix = 0 if p.idx == 1 else min(overlap, local_pages)
        retained_start = p.start + drop_prefix
        rows.append(
            {
                "idx": p.idx,
                "source_pages_1based": [p.start, p.end],
                "local_page_count": local_pages,
                "drop_prefix_pages_baseline": drop_prefix,
                "retained_source_pages_1based": [retained_start, p.end],
                "pdf_path": str(p.pdf_path.relative_to(work_dir)),
            }
        )
    payload = {
        "source_pdf": str(src_pdf),
        "source_page_count": parts[-1].end,
        "configured_body_pages": configured_body_pages,
        "effective_body_pages": effective_body_pages,
        "overlap": overlap,
        "page_idx_base": 0,
        "parts": rows,
        "status": "raw_parts_only",
        "note": "JSON/images 尚未合并，full.concat.md 尚未由 agent 去重；本 manifest 不进入最终产物目录。",
    }
    path = work_dir / "parts_manifest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"分卷清单: {path}")
    return path


def mineru_batch_upload(parts: list[Part], token: str, language: str = "ch", is_ocr: bool = False) -> str:
    """用 batch 接口拿上传 URL，依次 PUT 上传。返回 batch_id。"""
    files = [{"name": p.pdf_path.name, "is_ocr": is_ocr} for p in parts]
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


def mineru_wait_batch(
    batch_id: str,
    token: str,
    expected_count: int,
    poll_sec: int = 30,
) -> list[dict]:
    """轮询到 expected_count 个任务全部 done/failed；空结果不能误判为完成。"""
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
        if len(results) < expected_count:
            waiting = {"<batch>": f"waiting {len(results)}/{expected_count}"}
            if waiting != last_states:
                log(f"状态: waiting {len(results)}/{expected_count}")
                last_states = waiting
            time.sleep(poll_sec)
            continue
        states = {r["file_name"]: r.get("state", "?") for r in results}
        if states != last_states:
            summary = ", ".join(f"{n.split('_',1)[0]}={s}" for n, s in states.items())
            log(f"状态: {summary}")
            last_states = states
        pending = [r for r in results if r.get("state") not in ("done", "failed")]
        if not pending:
            return results
        time.sleep(poll_sec)


def download_and_extract(results: list[dict], parts: list[Part], work_dir: Path) -> list[Path]:
    """下载每个 part 的 full_zip 并解压到 work_dir/<part-name>/。返回各 part 的 full.md 路径。"""
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
        part_dir = work_dir / f"part{p.idx:02d}"
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


def write_concat_md(md_paths: list[Path], parts: list[Part], out_path: Path) -> None:
    """机械拼接并插入分卷标记；输出是待 agent 复核的中间稿，不是最终 full.md。"""
    lines: list[str] = []
    for p, md in zip(parts, md_paths):
        lines.append(f"\n\n<!-- === part {p.idx:02d} (pages {p.start}-{p.end}) === -->\n\n")
        lines.append(md.read_text(encoding="utf-8"))
    out_path.write_text("".join(lines), encoding="utf-8")
    log(f"合并完成 → {out_path} ({out_path.stat().st_size/1e6:.2f} MB)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="PDF URL 或本地路径")
    ap.add_argument(
        "--work-dir",
        "--out-dir",
        dest="work_dir",
        required=True,
        help="任务工作目录（part PDF、分卷解压结果、full.concat.md）；--out-dir 为兼容旧命令的别名",
    )
    ap.add_argument(
        "--state-dir",
        default="",
        help="任务状态目录（batch_id/results）；默认写到 work-dir 同级的隐藏目录，不污染正式产物目录",
    )
    ap.add_argument("--pages-per-part", type=int, default=198)
    ap.add_argument("--overlap", type=int, default=2)
    ap.add_argument("--language", default="ch")
    ap.add_argument("--token", default=os.environ.get("MINERU_TOKEN", ""), help="默认读 $MINERU_TOKEN")
    ap.add_argument("--skip-download", action="store_true", help="如 --input 已是本地文件，跳过下载")
    ap.add_argument("--skip-split", action="store_true", help="任务工作目录的 parts/ 下已有分卷时跳过拆分")
    ap.add_argument("--resume-batch", default="", help="复用已存在的 batch_id（跳过上传）")
    ap.add_argument("--ocr", action="store_true", default=False,
                    help="使用 OCR 模式（默认 is_ocr=false，对文本层 PDF 推荐；扫描件 / 图片 PDF 加此选项）")
    ap.add_argument("--insecure", action="store_true", default=False,
                    help="跳过 HTTPS 证书验证（仅用于自签证书场景）")
    args = ap.parse_args()

    if not args.token:
        sys.exit("未设置 MINERU_TOKEN")

    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    state_dir = (
        Path(args.state_dir).expanduser().resolve()
        if args.state_dir
        else work_dir.parent / f".{work_dir.name}.mineru-state"
    )
    state_dir.mkdir(parents=True, exist_ok=True)
    log(f"任务状态目录: {state_dir}")
    parts_dir = work_dir / "parts"
    parts_dir.mkdir(exist_ok=True)

    # 1. 准备原 PDF
    is_url = urlsplit(args.input).scheme in ("http", "https")
    if is_url:
        src_pdf = work_dir / "source.pdf"
        if args.skip_download and src_pdf.exists():
            log(f"已存在 {src_pdf}，跳过下载")
        elif src_pdf.exists():
            log(f"已存在 {src_pdf}，跳过下载")
        else:
            fetch_pdf(args.input, src_pdf, verify_ssl=not args.insecure)
    else:
        # fetch_pdf 对本地路径会先等待文件大小稳定，再返回原路径。
        src_pdf = fetch_pdf(args.input, work_dir / "source.pdf")

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

    write_parts_manifest(src_pdf, parts, work_dir, args.pages_per_part, args.overlap)

    # 3. 上传 + 轮询
    if args.resume_batch:
        batch_id = args.resume_batch
        log(f"复用 batch_id: {batch_id}")
    else:
        batch_id = mineru_batch_upload(parts, args.token, args.language, is_ocr=args.ocr)
        (state_dir / "batch_id.txt").write_text(batch_id)

    results = mineru_wait_batch(batch_id, args.token, expected_count=len(parts))
    (state_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))

    # 4. 下载原始分卷结果 + 生成待复核的机械拼接稿
    md_paths = download_and_extract(results, parts, work_dir)
    if len(md_paths) == len(parts):
        write_concat_md(md_paths, parts, work_dir / "full.concat.md")
        log("⚠ full.concat.md 仍含 overlap 与分卷标记，且 JSON/images 尚未合并；不得作为最终产物")
    else:
        log(f"⚠ 只成功 {len(md_paths)}/{len(parts)} 卷，未生成拼接稿")


if __name__ == "__main__":
    main()
