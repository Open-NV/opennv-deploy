from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_railway_contexts.py"
SPEC = importlib.util.spec_from_file_location("build_railway_contexts", SCRIPT)
assert SPEC and SPEC.loader
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class RailwayContextTests(unittest.TestCase):
    def fixture_workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        files = {
            "opennv-validation/backend/go.mod": "module example/backend\n",
            "opennv-validation/backend/go.sum": "",
            "opennv-validation/backend/cmd/server/main.go": "package main\nfunc main() {}\n",
            "opennv-validation/LICENSE": "license\n",
            "opennv-validation/web/package.json": '{"scripts":{"build":"true"}}\n',
            "opennv-validation/web/package-lock.json": "{}\n",
            "opennv-validation/web/src/main.ts": "export {};\n",
            "opennv-validation/web/.env.local": "SECRET=ignored\n",
            "opennv-validation/web/private.pem": "ignored\n",
            "opennv-validation/web/node_modules/ignored.js": "ignored\n",
            "opennv-validation/web/dist/ignored.js": "ignored\n",
            "clisynth/go.mod": "module example/clisynth\n",
            "clisynth/go.sum": "",
            "clisynth/cmd/clisynth/main.go": "package main\nfunc main() {}\n",
            "clisynth/LICENSE": "license\n",
            "outputfsm-packs/catalog/index.yaml": "apiVersion: v1\n",
            "outputfsm-packs/LICENSE": "license\n",
            "validation-packs/catalog/index.yaml": "apiVersion: v1\n",
            "validation-packs/LICENSE": "license\n",
        }
        for relative, contents in files.items():
            path = workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents)
        for platform in range(8):
            for command in range(20):
                output = workspace / "outputfsm-packs" / "packs" / f"platform_{platform}" / "commands" / f"show_{command}.yaml"
                validation = workspace / "validation-packs" / "validations" / f"platform_{platform}" / f"show_{command}.yaml"
                output.parent.mkdir(parents=True, exist_ok=True)
                validation.parent.mkdir(parents=True, exist_ok=True)
                output.write_text("apiVersion: v1\n")
                validation.write_text("apiVersion: v1\n")
        return workspace

    def test_contexts_are_complete_and_exclude_local_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            workspace = self.fixture_workspace(temporary_root)
            output = temporary_root / "contexts"
            manifest = BUILD.build_contexts(workspace, output)

            self.assertEqual(set(manifest["contexts"]), {"app", "clisynth"})
            self.assertTrue((output / "app" / "backend" / "go.mod").is_file())
            self.assertTrue((output / "app" / "web" / "package-lock.json").is_file())
            self.assertTrue((output / "app" / "validation-packs" / "catalog" / "index.yaml").is_file())
            self.assertTrue((output / "clisynth" / "outputfsm-packs" / "catalog" / "index.yaml").is_file())
            self.assertFalse((output / "app" / "web" / "node_modules").exists())
            self.assertFalse((output / "app" / "web" / "dist").exists())
            self.assertFalse((output / "app" / "web" / ".env.local").exists())
            self.assertFalse((output / "app" / "web" / "private.pem").exists())
            self.assertFalse(any(output.rglob(".git")))
            self.assertFalse(any(output.rglob("__pycache__")))

            context_manifest = json.loads((output / "app" / "BUILD-MANIFEST.json").read_text())
            self.assertEqual(set(context_manifest["deploymentTemplates"]), {"Dockerfile", "railway.json"})
            self.assertEqual(
                set(context_manifest["runtimeLicenses"]),
                {
                    "opennv-deploy.LICENSE",
                    "opennv-validation.LICENSE",
                    "outputfsm-packs.LICENSE",
                    "validation-packs.LICENSE",
                },
            )
            self.assertEqual(
                set(context_manifest["sources"]),
                {"backend", "web", "outputfsm-packs", "validation-packs"},
            )
            for source in context_manifest["sources"].values():
                self.assertTrue(source["files"])
                self.assertTrue(all(len(item["sha256"]) == 64 for item in source["files"]))

    def test_unsafe_output_path_is_rejected(self) -> None:
        with self.assertRaises(RuntimeError):
            BUILD.reset_output(ROOT.parent)

    def test_release_mode_rejects_uncommitted_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            workspace = self.fixture_workspace(temporary_root)
            output = temporary_root / "contexts"
            with self.assertRaisesRegex(RuntimeError, "committed, clean sources"):
                BUILD.build_contexts(workspace, output, require_clean=True)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
