# Build: pyinstaller TrenchRadar.spec   ->  dist/TrenchRadar(.exe)
from PyInstaller.utils.hooks import collect_submodules

hidden = (collect_submodules("uvicorn") + collect_submodules("radar") + collect_submodules("websockets")
          + collect_submodules("tokenizers")
          # numpy 2.x imports parts of numpy._core from C code, which PyInstaller's analysis misses
          # ("No module named 'numpy._core._exceptions'"); without them numpy, and with it onnxruntime,
          # fail inside the exe and the launch-edge model and semantic narratives switch off
          + collect_submodules("numpy") + collect_submodules("onnxruntime"))

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    datas=[("web", "web"), (".env.example", "."), ("radar/data", "radar/data"), ("THIRD_PARTY.md", ".")],
    hiddenimports=hidden,
    excludes=["pytest", "tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="TrenchRadar",
    console=True,          # the console window is the "app is running" indicator and log
    icon="web/icons/trench-radar.ico",    # scripts/brand_assets.py
    upx=False,
)
