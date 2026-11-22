"""Content-addressed local backups with verified, non-overwriting restore."""

import argparse
import hashlib
import json
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


def digest(data):
    return hashlib.sha256(data).hexdigest()


def snapshot(source, vault):
    source, vault = Path(source).resolve(), Path(vault).resolve()
    if not source.is_dir() or vault == source or source in vault.parents:
        raise ValueError("Source must be a directory; vault must be outside source")
    objects = vault / "objects"
    manifests = vault / "snapshots"
    objects.mkdir(parents=True, exist_ok=True)
    manifests.mkdir(exist_ok=True)
    entries = []
    for file in sorted(source.rglob("*")):
        if file.is_symlink():
            raise ValueError(f"Symlinks are unsupported: {file}")
        if not file.is_file():
            continue
        data = file.read_bytes()
        checksum = digest(data)
        blob = objects / checksum
        if blob.exists():
            if digest(blob.read_bytes()) != checksum:
                raise ValueError(f"Corrupt existing object: {checksum}")
        else:
            with tempfile.NamedTemporaryFile(dir=objects, delete=False) as tmp:
                tmp.write(data)
                temporary = Path(tmp.name)
            temporary.replace(blob)
        entries.append(
            dict(
                path=file.relative_to(source).as_posix(),
                sha256=checksum,
                size=len(data),
            )
        )
    identifier = uuid.uuid4().hex
    manifest = dict(
        version=1, created_at=datetime.now(timezone.utc).isoformat(), files=entries
    )
    target = manifests / f"{identifier}.json"
    with tempfile.NamedTemporaryFile(mode="w", dir=manifests, delete=False) as tmp:
        json.dump(manifest, tmp, indent=2)
        temporary = Path(tmp.name)
    temporary.replace(target)
    return identifier


def load_verified(vault, identifier):
    vault = Path(vault)
    if not re.fullmatch(r"[a-f0-9]{32}", identifier):
        raise ValueError("Invalid snapshot ID")
    manifest = json.loads((vault / "snapshots" / f"{identifier}.json").read_text())
    if manifest.get("version") != 1:
        raise ValueError("Unsupported manifest version")
    entries = manifest["files"]
    seen = set()
    for entry in entries:
        path = PurePosixPath(entry["path"])
        if (
            not entry["path"]
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in entry["path"]
            or ":" in entry["path"]
            or str(path) == "."
        ):
            raise ValueError("Unsafe restore path")
        normalized = str(path).casefold()
        if normalized in seen:
            raise ValueError("Duplicate restore path")
        seen.add(normalized)
        checksum = entry["sha256"]
        if not re.fullmatch(r"[a-f0-9]{64}", checksum):
            raise ValueError("Invalid object digest")
        blob = vault / "objects" / checksum
        data = blob.read_bytes()
        if len(data) != entry["size"] or digest(data) != checksum:
            raise ValueError(f"Corrupt object: {checksum}")
    return entries


def restore(vault, identifier, destination):
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Restore destination must not exist")
    entries = load_verified(vault, identifier)
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".restore-", dir=destination.parent))
    try:
        for entry in entries:
            target = stage / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            data = (Path(vault) / "objects" / entry["sha256"]).read_bytes()
            if digest(data) != entry["sha256"]:
                raise ValueError("Object changed during restore")
            target.write_bytes(data)
        # Reserve the final directory exclusively; refuse existing destinations.
        destination.mkdir()
        try:
            for child in stage.iterdir():
                shutil.move(str(child), destination / child.name)
        except Exception:
            shutil.rmtree(destination)
            raise
    finally:
        shutil.rmtree(stage)
    return len(entries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True, type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("snapshot").add_argument("source", type=Path)
    sub.add_parser("verify").add_argument("id")
    restore_parser = sub.add_parser("restore")
    restore_parser.add_argument("id")
    restore_parser.add_argument("destination", type=Path)
    sub.add_parser("list")
    args = parser.parse_args()
    try:
        if args.command == "snapshot":
            result = {"snapshot": snapshot(args.source, args.vault)}
        elif args.command == "verify":
            result = {"verified_files": len(load_verified(args.vault, args.id))}
        elif args.command == "restore":
            result = {"restored_files": restore(args.vault, args.id, args.destination)}
        else:
            result = {
                "snapshots": sorted(
                    p.stem for p in (args.vault / "snapshots").glob("*.json")
                )
            }
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"Operation failed: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
