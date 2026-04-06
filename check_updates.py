# /// script
# requires-python = ">=3.10"
# ///
"""
检查 skills-lock.json 中记录的外部 skills 是否有上游更新。
用法: uv run check_updates.py [--diff] [--skill <name>]
  --diff   显示有变化的 skill 的具体文件差异
  --skill  只检查指定的 skill
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

LOCK_FILE = Path(__file__).parent / "skills-lock.json"
LOCAL_SKILLS_DIR = Path(__file__).parent / "skills"

# 与 skills CLI 的 copyDirectory 保持一致的排除规则
EXCLUDE_FILES = {"metadata.json"}
EXCLUDE_DIRS = {".git", "__pycache__", "__pypackages__", "node_modules"}
MAX_RETRIES = 3


def _is_excluded(name: str, is_dir: bool = False) -> bool:
    if name in EXCLUDE_FILES:
        return True
    if name.startswith("."):
        return True
    if is_dir and name in EXCLUDE_DIRS:
        return True
    return False


def compute_hash(skill_dir: Path) -> str:
    """复现 skills CLI 的哈希算法，应用与 copyDirectory 相同的排除规则"""
    files = []
    for root, dirs, filenames in os.walk(skill_dir):
        # 就地修改 dirs 来跳过排除的目录
        dirs[:] = [d for d in dirs if not _is_excluded(d, is_dir=True)]
        for f in filenames:
            if _is_excluded(f):
                continue
            full = Path(root) / f
            # 统一使用 / 分隔符，与 JS 的 .split("\\").join("/") 一致
            rel = str(full.relative_to(skill_dir)).replace(os.sep, "/")
            files.append((rel, full.read_bytes()))
    files.sort(key=lambda x: x[0])
    h = hashlib.sha256()
    for rel_path, content in files:
        h.update(rel_path.encode())
        h.update(content)
    return h.hexdigest()


def download_tarball(repo: str, branch: str) -> bytes | None:
    """下载仓库 tarball，失败时重试"""
    url = f"https://github.com/{repo}/archive/refs/heads/{branch}.tar.gz"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = subprocess.run(
                ["curl", "-sL", "--max-time", "30", url],
                capture_output=True,
                check=True,
            )
            if result.stdout:
                return result.stdout
        except subprocess.CalledProcessError:
            pass
        if attempt < MAX_RETRIES:
            print(f"(重试 {attempt}/{MAX_RETRIES})...", end=" ", flush=True)
    return None


def download_skill(source: str, skill_name: str, tmp_dir: Path) -> Path | None:
    """从 GitHub 仓库下载指定 skill 到临时目录，自动探测目录结构"""
    if "#" in source:
        repo, branch = source.split("#", 1)
    else:
        repo, branch = source, "main"

    tarball = download_tarball(repo, branch)
    if not tarball:
        return None

    # 在 tarball 中查找 skill 的 SKILL.md 来确定实际路径
    list_result = subprocess.run(
        ["tar", "tz"], input=tarball, capture_output=True,
    )
    if list_result.returncode != 0:
        return None

    skill_prefix = None
    for line in list_result.stdout.decode().splitlines():
        if line.endswith(f"{skill_name}/SKILL.md"):
            skill_prefix = line.removesuffix("SKILL.md").rstrip("/")
            break

    if not skill_prefix:
        return None

    strip = skill_prefix.count("/")
    out_dir = tmp_dir / skill_name
    out_dir.mkdir(parents=True, exist_ok=True)

    tar_result = subprocess.run(
        ["tar", "xz", f"--strip-components={strip}", "-C", str(out_dir), skill_prefix],
        input=tarball, capture_output=True,
    )
    if tar_result.returncode != 0 or not any(out_dir.iterdir()):
        return None
    return out_dir


def show_diff(local_dir: Path, remote_dir: Path, skill_name: str):
    """显示两个目录之间的文件差异"""
    result = subprocess.run(
        ["diff", "-rN", "--color=always", "-u", str(local_dir), str(remote_dir)],
        capture_output=True, text=True,
    )
    if result.stdout:
        output = result.stdout
        output = output.replace(str(local_dir), f"local/{skill_name}")
        output = output.replace(str(remote_dir), f"remote/{skill_name}")
        print(output)
    else:
        print("  (文件内容相同但哈希不同，可能是权限或换行符差异)")


def main():
    parser = argparse.ArgumentParser(description="检查外部 skills 上游更新")
    parser.add_argument("--diff", action="store_true", help="显示具体文件差异")
    parser.add_argument("--skill", type=str, help="只检查指定的 skill")
    args = parser.parse_args()

    if not LOCK_FILE.exists():
        print(f"未找到 {LOCK_FILE}")
        sys.exit(1)

    lock_data = json.loads(LOCK_FILE.read_text())
    skills = lock_data.get("skills", {})

    github_skills = {
        name: info
        for name, info in skills.items()
        if info.get("sourceType") == "github"
    }

    if args.skill:
        if args.skill not in github_skills:
            print(f"skill '{args.skill}' 不在 lock 文件中或不是 GitHub 来源")
            sys.exit(1)
        github_skills = {args.skill: github_skills[args.skill]}

    if not github_skills:
        print("没有需要检查的 GitHub 来源 skills")
        return

    print(f"检查 {len(github_skills)} 个外部 skill 的上游更新...\n")

    updated = []
    unchanged = []
    failed = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        for name, info in sorted(github_skills.items()):
            source = info["source"]
            old_hash = info["computedHash"]
            print(f"  检查 {name} ({source})...", end=" ", flush=True)

            remote_dir = download_skill(source, name, tmp_path)
            if remote_dir is None or not any(remote_dir.iterdir()):
                print("❌ 下载失败")
                failed.append(name)
                continue

            new_hash = compute_hash(remote_dir)

            if new_hash == old_hash:
                print("✅ 无变化")
                unchanged.append(name)
            else:
                print(f"🔄 有更新")
                updated.append((name, source, old_hash, new_hash, remote_dir))

        print(f"\n{'='*50}")
        print(f"结果: {len(unchanged)} 个无变化, {len(updated)} 个有更新, {len(failed)} 个下载失败")

        if updated:
            print(f"\n有更新的 skills:")
            for name, source, old_hash, new_hash, remote_dir in updated:
                print(f"\n  📦 {name} ({source})")
                print(f"     旧哈希: {old_hash[:16]}...")
                print(f"     新哈希: {new_hash[:16]}...")

                if args.diff:
                    local_dir = LOCAL_SKILLS_DIR / name
                    if local_dir.exists():
                        print()
                        show_diff(local_dir, remote_dir, name)
                    else:
                        print(f"     (本地目录 {local_dir} 不存在，跳过 diff)")

            if not args.diff:
                print(f"\n提示: 使用 --diff 查看具体变化内容")

        if failed:
            print(f"\n下载失败的 skills: {', '.join(failed)}")


if __name__ == "__main__":
    main()
