"""Create a build inventory/SBOM from pinned public dependencies; no network."""

import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    records = json.loads((ROOT / "docs/security/release-dependencies-2026-09-10.json").read_text())
    lock = json.loads((ROOT / "vscode-extension/package-lock.json").read_text())
    components = []
    reviews = []
    for record in records:
        name, version = record["name"], record["version"]
        components.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:pypi/{name}@{version}",
                "hashes": [{"alg": "SHA-256", "content": a["sha256"]} for a in record["artifacts"]],
                "licenses": [{"license": {"name": record["license"] or "See package metadata"}}],
            }
        )
    for relative, record in lock["packages"].items():
        if not relative:
            continue
        name = relative.split("node_modules/")[-1]
        metadata = json.loads((ROOT / "vscode-extension" / relative / "package.json").read_text())
        integrity = record["integrity"].split("-", 1)
        components.append(
            {
                "type": "library",
                "name": name,
                "version": record["version"],
                "hashes": [{"alg": "SHA-512", "content": base64.b64decode(integrity[1]).hex()}]
                if integrity[0] == "sha512"
                else [],
            }
        )
        reviews.append(
            {
                "name": name,
                "version": record["version"],
                "development_only": record.get("dev", False),
                "license": metadata.get("license"),
                "lifecycle_scripts": {
                    k: v
                    for k, v in metadata.get("scripts", {}).items()
                    if k in ("preinstall", "install", "postinstall")
                },
            }
        )
    output = ROOT / "docs/security"
    (output / "release-sbom.cdx.json").write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.5",
                "version": 1,
                "components": components,
            },
            indent=2,
        )
        + "\n"
    )
    (output / "npm-license-inventory.json").write_text(json.dumps(reviews, indent=2) + "\n")
    print(
        json.dumps(
            {
                "components": len(components),
                "runtime_npm": [r["name"] for r in reviews if not r["development_only"]],
                "lifecycle_scripts": [r["name"] for r in reviews if r["lifecycle_scripts"]],
                "licenses": sorted({str(r["license"]) for r in reviews}),
            }
        )
    )


if __name__ == "__main__":
    main()
