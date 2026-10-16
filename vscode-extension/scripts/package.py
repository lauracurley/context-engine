#!/usr/bin/env python3
"""Build a dependency-free local VSIX; vendor only the engine's Python sources."""

import json
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent


def allowed_files(directory, suffixes):
    """Fail closed on symlinks and package only explicitly supported source assets."""
    if directory.is_symlink():
        raise ValueError("Refusing symlink package directory")
    for file in sorted(directory.rglob("*")):
        if file.is_symlink():
            raise ValueError("Refusing symlink package input")
        if file.is_file() and file.suffix in suffixes and "__pycache__" not in file.parts:
            yield file


def build():
    backend = ROOT / "backend"
    if any(p.is_symlink() for p in (backend, *backend.parents)):
        raise ValueError("Refusing symlink backend output")
    backend.mkdir(exist_ok=True)
    target = backend / "context_engine"
    if target.exists():
        shutil.rmtree(target)
    for source in allowed_files(REPO / "context_engine", {".py"}):
        dest_file = target / source.relative_to(REPO / "context_engine")
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest_file)
    (backend / "launch.py").write_text(
        'from context_engine.__main__ import main\n\nif __name__ == "__main__":\n    main()\n'
    )
    package = json.loads((ROOT / "package.json").read_text())
    ns = "http://schemas.microsoft.com/developer/vsx-schema/2011"
    ET.register_namespace("", ns)
    manifest = ET.Element("PackageManifest", {"Version": "2.0.0", "xmlns": ns})
    metadata = ET.SubElement(manifest, "Metadata")
    ET.SubElement(
        metadata,
        "Identity",
        {
            "Language": "en-US",
            "Id": package["name"],
            "Version": package["version"],
            "Publisher": package["publisher"],
        },
    )
    ET.SubElement(metadata, "DisplayName").text = package["displayName"]
    ET.SubElement(metadata, "Description", {"xml:space": "preserve"}).text = package["description"]
    ET.SubElement(metadata, "Categories").text = ",".join(package["categories"])
    ET.SubElement(metadata, "Tags").text = "context,mcp,codex,claude"
    properties = ET.SubElement(metadata, "Properties")
    for key, value in {
        "Microsoft.VisualStudio.Code.Engine": package["engines"]["vscode"],
        "Microsoft.VisualStudio.Code.ExtensionKind": "workspace",
        "Microsoft.VisualStudio.Code.ExecutesCode": "true",
    }.items():
        ET.SubElement(properties, "Property", {"Id": key, "Value": value})
    installation = ET.SubElement(manifest, "Installation")
    ET.SubElement(installation, "InstallationTarget", {"Id": "Microsoft.VisualStudio.Code"})
    ET.SubElement(manifest, "Dependencies")
    assets = ET.SubElement(manifest, "Assets")
    for kind, file in [
        ("Microsoft.VisualStudio.Code.Manifest", "package.json"),
        ("Microsoft.VisualStudio.Services.Content.Details", "README.md"),
    ]:
        ET.SubElement(
            assets, "Asset", {"Type": kind, "Path": "extension/" + file, "Addressable": "true"}
        )
    types = ET.Element(
        "Types", {"xmlns": "http://schemas.openxmlformats.org/package/2006/content-types"}
    )
    for suffix, mime in {
        "json": "application/json",
        "js": "application/javascript",
        "py": "text/plain",
        "md": "text/markdown",
        "svg": "image/svg+xml",
        "css": "text/css",
        "vsixmanifest": "text/xml",
    }.items():
        ET.SubElement(types, "Default", {"Extension": suffix, "ContentType": mime})
    dest = REPO / "dist" / ("context-engine-" + package["version"] + ".vsix")
    dest.parent.mkdir(exist_ok=True)
    files = [ROOT / "package.json", ROOT / "README.md", ROOT / "CHANGELOG.md"]
    for directory, suffixes in [
        ("src", {".js"}),
        ("media", {".js", ".css", ".svg"}),
        ("backend", {".py"}),
    ]:
        files.extend(allowed_files(ROOT / directory, suffixes))
    if any(file.is_symlink() for file in files):
        raise ValueError("Refusing symlink package input")
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "extension.vsixmanifest", ET.tostring(manifest, encoding="utf-8", xml_declaration=True)
        )
        archive.writestr(
            "[Content_Types].xml", ET.tostring(types, encoding="utf-8", xml_declaration=True)
        )
        for file in sorted(files):
            archive.write(file, "extension/" + file.relative_to(ROOT).as_posix())
    print(dest)
    return dest


if __name__ == "__main__":
    build()
