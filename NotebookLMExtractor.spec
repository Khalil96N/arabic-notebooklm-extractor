# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all


datas = [("web", "web"), ("app/resources", "app/resources")]
hiddenimports = []

for package in (
    "playwright",
    "pydantic",
    "pydantic_settings",
    "docx",
    "rich",
    "pymorphy3",
    "pymorphy3_dicts_ru",
    "dawg2_python",
):
    package_datas, package_binaries, package_hiddenimports = collect_all(
        package
    )
    datas += package_datas
    hiddenimports += package_hiddenimports

server_a = Analysis(
    ["web_app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
    optimize=0,
)
server_pyz = PYZ(server_a.pure)

server_exe = EXE(
    server_pyz,
    server_a.scripts,
    [],
    exclude_binaries=True,
    name="NotebookLMExtractor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

worker_a = Analysis(
    ["worker_app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
    optimize=0,
)
worker_pyz = PYZ(worker_a.pure)

worker_exe = EXE(
    worker_pyz,
    worker_a.scripts,
    [],
    exclude_binaries=True,
    name="NotebookLMWorker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    server_exe,
    worker_exe,
    server_a.binaries,
    server_a.datas,
    worker_a.binaries,
    worker_a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="NotebookLMExtractor",
)
