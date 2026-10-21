# Build: pyinstaller TrenchRadar.spec   ->  dist/TrenchRadar(.exe)
from PyInstaller.utils.hooks import collect_submodules

hidden = collect_submodules("uvicorn") + collect_submodules("radar") + collect_submodules("websockets")

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    datas=[("web", "web"), (".env.example", ".")],
    hiddenimports=hidden,
    excludes=["pytest", "tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="TrenchRadar",
    console=True,          # the console window is the "app is running" indicator and log
    upx=False,
)
