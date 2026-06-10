#!/usr/bin/env python3
"""Export a clean FOG template directory from the current source workspace."""

from __future__ import annotations

import argparse
import fnmatch
import shutil
import sys
from pathlib import Path


MANIFEST_DEFAULT = "config/template_manifest.yaml"
LIST_KEYS = ("managed_dirs", "managed_files", "protected_paths", "ignored_patterns")


def normalize(value: str) -> str:
    return value.replace("\\", "/").strip("/")


def parse_manifest(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        raise FileNotFoundError(f"manifest not found: {path}")

    manifest: dict[str, list[str]] = {key: [] for key in LIST_KEYS}
    section: str | None = None
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        content = line.split("#", 1)[0].rstrip()
        if not content.strip():
            continue

        stripped = content.strip()
        if stripped.endswith(":") and not stripped.startswith("-"):
            section = stripped[:-1].strip()
            manifest.setdefault(section, [])
            continue

        if stripped.startswith("- "):
            if not section:
                raise ValueError(f"list item before section at {path}:{line_no}")
            value = stripped[2:].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            manifest.setdefault(section, []).append(normalize(value))

    return {key: [normalize(item) for item in manifest.get(key, [])] for key in LIST_KEYS}


def glob_match(relative_path: str, pattern: str) -> bool:
    path = normalize(relative_path)
    pat = normalize(pattern)
    if "*" not in pat and "?" not in pat:
        return path == pat or path.startswith(f"{pat}/")
    return fnmatch.fnmatchcase(path, pat)


def is_workspace_gitkeep(relative_path: str) -> bool:
    path = normalize(relative_path)
    return path.startswith("workspace/") and path.endswith("/.gitkeep")


def is_protected(relative_path: str, patterns: list[str]) -> bool:
    path = normalize(relative_path)
    if is_workspace_gitkeep(path):
        return False
    if path.startswith("workspace/"):
        return True
    return any(glob_match(path, pattern) for pattern in patterns)


def is_ignored(relative_path: str, patterns: list[str]) -> bool:
    path = normalize(relative_path)
    name = Path(path).name
    return any(glob_match(path, pattern) or glob_match(name, pattern) for pattern in patterns)


def prepare_output(source_root: Path, output: Path, clean: bool, dry_run: bool) -> Path:
    source = source_root.resolve()
    target = output.expanduser().resolve()

    if target == source:
        raise ValueError("output path cannot be the source workspace itself")
    if source in target.parents:
        raise ValueError("output path must be outside the source workspace")

    if dry_run:
        return target

    if target.exists():
        if not target.is_dir():
            raise ValueError(f"output path exists but is not a directory: {target}")
        has_content = any(target.iterdir())
        if has_content and not clean:
            raise ValueError(f"output directory is not empty, rerun with --clean: {target}")
        if has_content and clean:
            shutil.rmtree(target)

    target.mkdir(parents=True, exist_ok=True)
    return target


def copy_file(source_root: Path, target_root: Path, relative_path: str, dry_run: bool) -> None:
    source = source_root / relative_path
    target = target_root / relative_path
    print(f"[COPY] {relative_path}")
    if dry_run:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def iter_managed_dir_files(
    source_root: Path,
    relative_dir: str,
    protected: list[str],
    ignored: list[str],
) -> list[str]:
    source_dir = source_root / relative_dir
    if not source_dir.exists():
        print(f"[WARN] managed dir missing: {relative_dir}")
        return []
    if not source_dir.is_dir():
        print(f"[WARN] managed dir is not a directory: {relative_dir}")
        return []

    def walk(current: Path) -> None:
        for item in current.iterdir():
            relative_path = normalize(str(item.relative_to(source_root)))
            if item.is_symlink():
                print(f"[WARN] skip symlink: {relative_path}")
                continue
            if item.is_dir():
                if is_protected(relative_path, protected):
                    print(f"[SKIP] protected dir: {relative_path}")
                    continue
                if is_ignored(relative_path, ignored):
                    print(f"[SKIP] ignored dir: {relative_path}")
                    continue
                walk(item)
                continue
            if item.is_file():
                files.append(relative_path)

    files: list[str] = []
    walk(source_dir)
    return files


def export_template(source_root: Path, target_root: Path, manifest: dict[str, list[str]], dry_run: bool) -> int:
    protected = manifest["protected_paths"]
    ignored = manifest["ignored_patterns"]
    copied = 0
    skipped = 0
    seen: set[str] = set()

    candidates: list[str] = []
    for relative_dir in manifest["managed_dirs"]:
        candidates.extend(iter_managed_dir_files(source_root, relative_dir, protected, ignored))
    candidates.extend(manifest["managed_files"])

    for relative_path in candidates:
        relative_path = normalize(relative_path)
        if relative_path in seen:
            continue
        seen.add(relative_path)

        source = source_root / relative_path
        if is_protected(relative_path, protected):
            print(f"[SKIP] protected: {relative_path}")
            skipped += 1
            continue
        if is_ignored(relative_path, ignored):
            print(f"[SKIP] ignored: {relative_path}")
            skipped += 1
            continue
        if not source.exists():
            print(f"[WARN] managed file missing: {relative_path}")
            skipped += 1
            continue
        if source.is_dir():
            print(f"[WARN] managed file is a directory: {relative_path}")
            skipped += 1
            continue

        copy_file(source_root, target_root, relative_path, dry_run)
        copied += 1

    print("")
    print(f"copied: {copied}")
    print(f"skipped: {skipped}")
    print(f"output: {target_root}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export a clean FOG template directory.")
    parser.add_argument("--source", default=".", help="source FOG workspace, defaults to current directory")
    parser.add_argument("--output", required=True, help="target template directory; must be outside source")
    parser.add_argument("--manifest", default=MANIFEST_DEFAULT, help="template manifest path")
    parser.add_argument("--clean", action="store_true", help="delete existing output directory before export")
    parser.add_argument("--dry-run", action="store_true", help="print planned files without copying")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    source_root = Path(args.source).expanduser().resolve()
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = source_root / manifest_path

    try:
        manifest = parse_manifest(manifest_path)
        target_root = prepare_output(source_root, Path(args.output), args.clean, args.dry_run)
        return export_template(source_root, target_root, manifest, args.dry_run)
    except Exception as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
