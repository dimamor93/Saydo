from PyInstaller.utils.hooks import collect_all

gigaam_datas, gigaam_binaries, gigaam_hiddenimports = collect_all("gigaam")
pyannote_datas, pyannote_binaries, pyannote_hiddenimports = collect_all("pyannote.audio")

datas = [
    ("assets", "assets"),
]

datas += gigaam_datas
datas += pyannote_datas

binaries = []
binaries += gigaam_binaries
binaries += pyannote_binaries

hiddenimports = []
hiddenimports += gigaam_hiddenimports
hiddenimports += pyannote_hiddenimports

hiddenimports += [
    "pystray",
    "PIL",
    "PIL.Image",
    "sounddevice",
    "numpy",
    "torch",
    "torchaudio",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Saydo",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/saydo-tray.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Saydo",
)