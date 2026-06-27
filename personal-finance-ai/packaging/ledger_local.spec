# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

project_root = Path(SPECPATH).resolve().parent
backend_root = project_root / "backend"

datas = [
    (str(project_root / "frontend" / "dist"), "frontend_dist"),
    (str(project_root / "docs"), "docs"),
]
binaries = []
hiddenimports = collect_submodules("chromadb")

for package in ("chromadb", "pymupdf", "reportlab"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

analysis = Analysis(
    [str(backend_root / "desktop_main.py")],
    pathex=[str(backend_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "ruff"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Ledger Local",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch=None,
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="Ledger Local",
)

app = BUNDLE(
    collection,
    name="Ledger Local.app",
    bundle_identifier="local.ledger.finance",
    info_plist={
        "CFBundleDisplayName": "Ledger Local",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "LSApplicationCategoryType": "public.app-category.finance",
        "NSHighResolutionCapable": True,
    },
)
