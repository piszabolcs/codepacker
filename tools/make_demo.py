# -*- coding: utf-8 -*-
#
# the synthetic demo project and the README screenshots
#
#   python tools/make_demo.py DIR             writes the demo project ("shop-app") into DIR
#   python tools/make_demo.py --screenshots   regenerates docs/screenshots/*.png
#
# the demo has about 30 files in several languages plus obviously fake secrets (assembled at
# runtime, so this file holds none); the screenshots are taken offscreen with QWidget.grab(),
# never on a screen, and every visible text is checked for the real temp path and user name

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOTS = REPO_ROOT / "docs" / "screenshots"
SHOWN_PARENT = "C:\\demo"           # what the screenshots show instead of the temp folder

DASHES = "-" * 5
FAKE_KEY = (f"{DASHES}BEGIN OPENSSH PRIVATE KEY{DASHES}\nDEMO-ONLY-NOT-A-REAL-KEY\n"
            f"{DASHES}END OPENSSH PRIVATE KEY{DASHES}\n")
FAKE_OPENAI_KEY = "sk-" + "demo" * 12
FAKE_GITHUB_TOKEN = "ghp_" + "DEMO" * 9

DEMO_FILES = {
    "README.md": "# Shop app\n\nA tiny demo shop: Python API, TypeScript front end, Go worker.\n",
    "LICENSE": "Demo licence text.\n",
    "Dockerfile": "FROM python:3.12-slim\nCOPY src/server /app\nCMD [\"python\", \"/app/app.py\"]\n",
    "Makefile": "test:\n\tpython -m pytest\n",
    ".gitignore": "node_modules/\n.env\n",
    "package.json": '{\n  "name": "shop-web",\n  "private": true\n}\n',
    "package-lock.json": '{\n  "lockfileVersion": 3\n}\n',
    "tsconfig.json": '{\n  "compilerOptions": {"strict": true}\n}\n',
    ".github/workflows/ci.yml": "on: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n",
    "src/server/app.py": "from routes import register\n\n\ndef main():\n    register()\n",
    "src/server/routes.py": "def register():\n    print('GET /products')\n",
    "src/server/models.py": "class Product:\n    def __init__(self, name, price):\n"
                            "        self.name = name\n        self.price = price\n",
    "src/server/config.py": f'OPENAI_API_KEY = "{FAKE_OPENAI_KEY}"\nDEBUG = False\n',
    "src/web/index.html": "<!doctype html>\n<title>Shop</title>\n<div id=\"app\"></div>\n",
    "src/web/styles.css": "body { font-family: sans-serif; }\n",
    "src/web/main.ts": "import { renderCart } from './components/Cart';\n\nrenderCart();\n",
    "src/web/components/Cart.tsx": "export function Cart() {\n  return <aside>Cart</aside>;\n}\n",
    "src/web/components/ProductList.tsx": "export function ProductList() {\n"
                                          "  return <ul></ul>;\n}\n",
    "src/worker/main.go": "package main\n\nfunc main() { Run() }\n",
    "src/worker/queue.go": "package main\n\nfunc Run() {}\n",
    "src/pricing/lib.rs": "pub fn total(prices: &[u32]) -> u32 {\n    prices.iter().sum()\n}\n",
    "scripts/deploy.sh": f"#!/bin/sh\nexport GITHUB_TOKEN={FAKE_GITHUB_TOKEN}\n./release.sh\n",
    "scripts/setup.ps1": "Write-Host 'Setting up the shop'\n",
    "docs/architecture.md": "# Architecture\n\nAPI, web front end and a queue worker.\n",
    "tests/test_routes.py": "def test_register():\n    assert True\n",
    "config/settings.yaml": "currency: EUR\npage_size: 20\n",
    # what never goes in
    ".env": "DATABASE_PASSWORD=demo-only-not-a-real-password\n",
    "config/credentials.json": '{"user": "demo", "password": "demo-only"}\n',
    "keys/id_ed25519": FAKE_KEY,
    "node_modules/left-pad/index.js": "module.exports = () => '';\n",
    "assets/logo.png": "\x89PNG demo bytes\n",
    "server.log": "demo log line\n",
}
AD_HOC = ["README.md", "src/server/app.py", "src/server/config.py", "src/web/main.ts", ".env"]


def write_demo(root):
    root = Path(root)
    for relative, content in DEMO_FILES.items():
        path = root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
    return root


# ------------------------------------------------------------------------------------------------
# screenshots
# ------------------------------------------------------------------------------------------------


def _wait(app, condition, seconds=30):
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > deadline:
            raise TimeoutError("the window did not finish in time")
        app.processEvents()
        time.sleep(0.01)


def _visible_texts(widget):
    from PySide6.QtCore import QModelIndex
    from PySide6.QtWidgets import (
        QAbstractButton, QAbstractItemView, QComboBox, QLabel, QLineEdit, QPlainTextEdit,
        QWidget,
    )

    texts = []
    for child in [widget, *widget.findChildren(QWidget)]:
        if not child.isVisible():
            continue    # not in the picture (a closed drop-down, the folded settings)
        if isinstance(child, (QLabel, QAbstractButton, QLineEdit)):
            texts.append(child.text())
        elif isinstance(child, QPlainTextEdit):
            texts.append(child.toPlainText())
        elif isinstance(child, QComboBox):
            texts.append(child.currentText())
        elif isinstance(child, QAbstractItemView) and child.model() is not None:
            model = child.model()
            pending = [QModelIndex()]
            while pending:
                parent = pending.pop()
                for row in range(model.rowCount(parent)):
                    for column in range(model.columnCount(parent)):
                        texts.append(str(model.index(row, column, parent).data() or ""))
                    pending.append(model.index(row, 0, parent))
    if hasattr(widget, "statusBar"):
        texts.append(widget.statusBar().currentMessage())
    return texts


def _check_private(widget, private):
    leaks = [text for text in _visible_texts(widget)
             for secret in private if secret and secret.lower() in text.lower()]
    if leaks:
        raise RuntimeError("a screenshot would show a real path or name: {!r}".format(leaks[0]))


def _mask(window, real_parent):
    # the temp folder becomes C:\demo in every text the window shows
    window.project_edit.setText(window.project_edit.text().replace(real_parent, SHOWN_PARENT))
    window.log_view.setPlainText(window.log_view.toPlainText().replace(real_parent, SHOWN_PARENT))


def take_screenshots(target=SCREENSHOTS):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    fonts = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
    if os.path.isdir(fonts):
        os.environ.setdefault("QT_QPA_FONTDIR", fonts)
    sys.path.insert(0, str(REPO_ROOT))
    work = Path(tempfile.mkdtemp(prefix="codepacker-demo-"))
    os.environ["APPDATA"] = str(work / "appdata")

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox

    from codepacker import APP_NAME, settings
    settings.settings_file_override = str(work / "appdata" / "CodePacker" / "settings.ini")
    from codepacker.ui.main_window import MainWindow
    from codepacker.ui.signature import AboutDialog

    real_parent = str(work)
    private = [real_parent, os.environ.get("USERNAME", ""), os.path.expanduser("~")]
    demo = write_demo(work / "shop-app")
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.show()
    window.resize(1240, 820)

    def shoot(widget, name):
        app.processEvents()
        _check_private(widget, private)
        widget.grab().save(str(target / name), "PNG")
        print("written:", target / name)

    window.project_edit.setText(str(demo))
    window.start_scan()
    _wait(app, lambda: not window.busy)
    _mask(window, real_parent)
    shoot(window, "main-window.png")

    window.settings_toggle.setChecked(True)
    window.b64_checkbox.setChecked(True)
    shoot(window, "settings.png")
    window.settings_toggle.setChecked(False)

    window.side_tabs.setCurrentIndex(2)
    shoot(window, "excluded.png")
    window.side_tabs.setCurrentIndex(0)

    shown = []
    QMessageBox.information = staticmethod(lambda parent, title, text: shown.append(text))
    QMessageBox.warning = QMessageBox.information
    window.start_pack()
    _wait(app, lambda: not window.busy and shown)
    result = QMessageBox(QMessageBox.Icon.Information, APP_NAME,
                         shown[-1].replace(real_parent, SHOWN_PARENT),
                         QMessageBox.StandardButton.Ok, window)
    result.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    result.show()
    shoot(result, "build-result.png")
    result.close()

    about = AboutDialog(window)
    about.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    about.show()
    shoot(about, "about.png")
    about.close()

    window.start_selection_scan([str(demo.joinpath(*path.split("/"))) for path in AD_HOC])
    _wait(app, lambda: not window.busy)
    _mask(window, real_parent)
    shoot(window, "ad-hoc.png")
    window.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write the demo project or the screenshots.")
    parser.add_argument("target", nargs="?", help="folder for the demo project")
    parser.add_argument("--screenshots", action="store_true",
                        help="regenerate docs/screenshots/*.png from the demo project")
    arguments = parser.parse_args(argv)
    if arguments.screenshots:
        take_screenshots()
    elif arguments.target:
        print("written:", write_demo(Path(arguments.target) / "shop-app"))
    else:
        parser.error("give a target folder or --screenshots")
    return 0


if __name__ == "__main__":
    sys.exit(main())
