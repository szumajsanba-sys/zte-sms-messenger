import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASE_DIR = ROOT / "release"
DIST_DIR = ROOT / "dist" / "ZTE-SMS-Messenger"


def build() -> None:
    print("Building ZTE SMS Messenger executable with PyInstaller...")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--console",
        "--name", "ZTE-SMS-Messenger",
        "--add-data", f"{ROOT / 'web'}{os.pathsep}web",
        "--add-data", f"{ROOT / 'standalone_viewer'}{os.pathsep}standalone_viewer",
        "main.py",
    ]
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"\nPyInstaller build failed with exit code: {result.returncode}")
        sys.exit(result.returncode)

    print("\nBuild successful! Output located in dist/ZTE-SMS-Messenger/")

    # Package into release zip
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    zip_dest = RELEASE_DIR / "ZTE-SMS-Messenger-Windows-x64"
    print(f"Creating release archive: {zip_dest}.zip ...")

    shutil.make_archive(
        base_name=str(zip_dest),
        format="zip",
        root_dir=str(DIST_DIR.parent),
        base_dir="ZTE-SMS-Messenger",
    )
    print(f"Release archive successfully generated at: {zip_dest}.zip")


if __name__ == "__main__":
    build()
