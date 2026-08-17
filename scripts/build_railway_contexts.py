#!/usr/bin/env python3
"""Assemble deterministic Railway build contexts from sibling OpenNV repos."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

DEPLOY_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = DEPLOY_ROOT.parent
DEFAULT_OUTPUT = DEPLOY_ROOT / ".generated" / "railway"

EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "artifacts",
    "coverage",
    "dist",
    "node_modules",
    "test-results",
}
EXCLUDED_FILES = {".DS_Store"}

SOURCES = {
    "backend": Path("opennv-validation/backend"),
    "web": Path("opennv-validation/web"),
    "clisynth": Path("clisynth"),
    "outputfsm-packs": Path("outputfsm-packs"),
    "validation-packs": Path("validation-packs"),
}

RUNTIME_LICENSES = {
    "app": {
        "opennv-deploy.LICENSE": DEPLOY_ROOT / "LICENSE",
        "opennv-validation.LICENSE": WORKSPACE_ROOT / "opennv-validation" / "LICENSE",
        "outputfsm-packs.LICENSE": WORKSPACE_ROOT / "outputfsm-packs" / "LICENSE",
        "validation-packs.LICENSE": WORKSPACE_ROOT / "validation-packs" / "LICENSE",
    },
    "clisynth": {
        "opennv-deploy.LICENSE": DEPLOY_ROOT / "LICENSE",
        "clisynth.LICENSE": WORKSPACE_ROOT / "clisynth" / "LICENSE",
        "outputfsm-packs.LICENSE": WORKSPACE_ROOT / "outputfsm-packs" / "LICENSE",
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_revision(path: Path) -> dict[str, object]:
    try:
        revision = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "-C", str(path), "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except subprocess.CalledProcessError:
        revision = "uncommitted"
        dirty = True
    return {"revision": revision, "dirty": dirty}


def include_path(path: Path) -> bool:
    if any(part in EXCLUDED_DIRS for part in path.parts) or path.name in EXCLUDED_FILES:
        return False
    if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
        return False
    if path.suffix.lower() in {".key", ".pem", ".p12", ".pfx"}:
        return False
    return path.name not in {"id_dsa", "id_ecdsa", "id_ed25519", "id_rsa"}


def copy_source(source: Path, destination: Path) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if not include_path(relative):
            continue
        if path.is_symlink():
            raise RuntimeError(f"refusing symlink in deploy source: {path}")
        if not path.is_file():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        files.append(
            {
                "path": relative.as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return files


def reset_output(output: Path) -> None:
    resolved = output.resolve()
    forbidden = {Path("/").resolve(), DEPLOY_ROOT.resolve(), WORKSPACE_ROOT.resolve()}
    if resolved in forbidden or len(resolved.parts) < 4:
        raise RuntimeError(f"refusing unsafe output path: {resolved}")
    if output.is_symlink():
        raise RuntimeError(f"refusing symlink output path: {output}")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)


def validate_sources(workspace: Path) -> None:
    missing = [str(workspace / relative) for relative in SOURCES.values() if not (workspace / relative).is_dir()]
    if missing:
        raise RuntimeError("missing source directories: " + ", ".join(missing))

    output_definitions = list((workspace / SOURCES["outputfsm-packs"] / "packs").glob("*/commands/*.yaml"))
    validation_definitions = list((workspace / SOURCES["validation-packs"] / "validations").glob("*/*.yaml"))
    output_platforms = {item.parent.parent.name for item in output_definitions}
    validation_platforms = {item.parent.name for item in validation_definitions}
    if len(output_definitions) != 160 or len(output_platforms) != 8:
        raise RuntimeError(
            f"OutputFSM pack must contain 160 definitions across 8 platforms; found "
            f"{len(output_definitions)} across {len(output_platforms)}"
        )
    if len(validation_definitions) != 160 or len(validation_platforms) != 8:
        raise RuntimeError(
            f"validation pack must contain 160 definitions across 8 platforms; found "
            f"{len(validation_definitions)} across {len(validation_platforms)}"
        )


def runtime_licenses(workspace: Path, context_name: str) -> dict[str, Path]:
    licenses = dict(RUNTIME_LICENSES[context_name])
    for name, path in tuple(licenses.items()):
        if path.is_relative_to(DEPLOY_ROOT):
            continue
        try:
            relative = path.relative_to(WORKSPACE_ROOT)
        except ValueError:
            continue
        licenses[name] = workspace / relative
    return licenses


def build_contexts(workspace: Path, output: Path, require_clean: bool = False) -> dict[str, object]:
    validate_sources(workspace)
    revisions = {name: source_revision(workspace / relative) for name, relative in SOURCES.items()}
    if require_clean:
        dirty = [name for name, metadata in revisions.items() if metadata["dirty"]]
        if dirty:
            raise RuntimeError("release contexts require committed, clean sources: " + ", ".join(dirty))
    reset_output(output)

    manifest: dict[str, object] = {
        "schemaVersion": 1,
        "sources": {},
        "deploymentTemplates": {},
        "contexts": {
            "app": ["backend", "web", "outputfsm-packs", "validation-packs"],
            "clisynth": ["clisynth", "outputfsm-packs"],
        },
    }
    for name, relative in SOURCES.items():
        source = workspace / relative
        staging = output / ".sources" / name
        files = copy_source(source, staging)
        manifest["sources"][name] = {
            "path": relative.as_posix(),
            **revisions[name],
            "files": files,
        }

    for context_name, source_names in manifest["contexts"].items():
        context = output / context_name
        context.mkdir(parents=True)
        for name in source_names:
            shutil.copytree(output / ".sources" / name, context / name)
        dockerfile = DEPLOY_ROOT / "railway" / "docker" / f"{context_name}.Dockerfile"
        railway_config = DEPLOY_ROOT / "railway" / "config" / f"{context_name}.railway.json"
        shutil.copy2(dockerfile, context / "Dockerfile")
        shutil.copy2(railway_config, context / "railway.json")
        licenses: dict[str, dict[str, object]] = {}
        for license_name, license_source in runtime_licenses(workspace, context_name).items():
            if not license_source.is_file():
                raise RuntimeError(f"missing runtime license: {license_source}")
            license_target = context / "licenses" / license_name
            license_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(license_source, license_target)
            licenses[license_name] = {
                "sha256": sha256_file(license_source),
                "bytes": license_source.stat().st_size,
            }
        templates = {
            "Dockerfile": {"sha256": sha256_file(dockerfile), "bytes": dockerfile.stat().st_size},
            "railway.json": {"sha256": sha256_file(railway_config), "bytes": railway_config.stat().st_size},
        }
        manifest["deploymentTemplates"][context_name] = templates
        context_manifest = {
            "schemaVersion": 1,
            "context": context_name,
            "deploymentTemplates": templates,
            "runtimeLicenses": licenses,
            "sources": {name: manifest["sources"][name] for name in source_names},
        }
        (context / "BUILD-MANIFEST.json").write_text(
            json.dumps(context_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    shutil.rmtree(output / ".sources")
    (output / "BUILD-MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=WORKSPACE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="fail unless every source is a clean committed Git checkout",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_contexts(args.workspace.resolve(), args.output.resolve(), require_clean=args.require_clean)
    source_count = len(manifest["sources"])
    print(f"assembled 2 Railway contexts from {source_count} independent source trees at {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
