# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ["Main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("web/index.html", "web"),
        ("web/controle.html", "web"),
        ("web/css/telao.css", "web/css"),
        ("web/css/controle.css", "web/css"),
        ("web/js/telao.js", "web/js"),
        ("web/js/controle.js", "web/js"),
        ("assets/logoX8.svg", "assets"),
        ("assets/LogoFlowerEngenharia.png", "assets"),
        ("assets/ContagemRegressiva.wav", "assets"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SistemaCorridaRC",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
