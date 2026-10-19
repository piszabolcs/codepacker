# -*- mode: python ; coding: utf-8 -*-
#
# this is the pyinstaller spec file, it says how the exe should be built
# run with: build.bat  (or: .venv\Scripts\pyinstaller codepacker.spec --noconfirm)
#
# if you want to change something, the few lines below are almost certainly enough

import os
import sys

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

# the name and the version come from the package itself, so they are written down only once
# (SPECPATH is the folder of this file, PyInstaller defines it)
sys.path.insert(0, SPECPATH)
from codepacker import APP_NAME, __version__  # noqa: E402

# ------------------------------------------------------------
# SETTINGS
# ------------------------------------------------------------

EXE_NAME = APP_NAME

# set this to True for a single exe file
# set it to False for a faster startup, if a folder instead of one file is fine
ONEFILE = True

# if True, no black console window opens alongside the app
NO_CONSOLE = True


# ------------------------------------------------------------
# NO NEED TO TOUCH ANYTHING BELOW THIS POINT
# ------------------------------------------------------------


def write_version_file(path):
    # the version resource shown in the exe's Properties > Details tab,
    # generated on every build from codepacker.__version__
    numbers = tuple(int(part) for part in __version__.split(".")) + (0,)
    info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
        kids=[
            StringFileInfo([
                StringTable("040904B0", [
                    StringStruct("FileDescription", APP_NAME),
                    StringStruct("FileVersion", __version__),
                    StringStruct("InternalName", EXE_NAME),
                    StringStruct("OriginalFilename", EXE_NAME + ".exe"),
                    StringStruct("ProductName", APP_NAME),
                    StringStruct("ProductVersion", __version__),
                ]),
            ]),
            VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
        ],
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(str(info))
    return path


version_file = write_version_file(os.path.join(SPECPATH, "build", "version_info.txt"))

# the assets folder has to be bundled into the exe, otherwise there's no icon
data_files = [
    ("assets/icon.ico", "assets"),
    ("assets/icon_256.png", "assets"),
]

# these Qt modules aren't used, we exclude them to keep the exe smaller
excluded_modules = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtNetwork",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtXml",
    "PySide6.QtQml",
    "tkinter",
    "unittest",
    "pydoc",
    "email",
    "http",
    "xml",
    "numpy",
    "PIL",
    "matplotlib",
    "scipy",
    "pandas",
]

analysis = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=data_files,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

if ONEFILE:
    # a single exe, everything bundled inside
    exe = EXE(
        pyz,
        analysis.scripts,
        analysis.binaries,
        analysis.datas,
        [],
        name=EXE_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=not NO_CONSOLE,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon="assets/icon.ico",
        version=version_file,
    )
else:
    # folder variant, starts up faster
    exe = EXE(
        pyz,
        analysis.scripts,
        [],
        exclude_binaries=True,
        name=EXE_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=not NO_CONSOLE,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon="assets/icon.ico",
        version=version_file,
    )

    coll = COLLECT(
        exe,
        analysis.binaries,
        analysis.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name=EXE_NAME,
    )
