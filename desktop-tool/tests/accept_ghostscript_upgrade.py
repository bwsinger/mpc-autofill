"""Destructive installer acceptance: disposable GitHub-hosted runners ONLY; no GUI consent coverage."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import icc, pdf_maker

import autofill

OLD_WINDOWS_URL = "https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/gs10040/gs10040w64.exe"
# Artifex's gs10040/SHA512SUMS, retained with the acceptance evidence.
OLD_WINDOWS_SHA512 = "1de01b22c1a351ab2ac44ecb639c38b6050e833985b3b73bf3144ba14ee8f3e825d5fec9e4f82da6fea60513e41f3aef6bfb120338e26642348c5193a1e00120"
OLD_MACOS = (
    "https://pages.uoregon.edu/koch/Ghostscript-10.04.0.pkg",
    "6b54e7b0ffe63a54b774a820794085bc3ce253f7b339d4485d3263be76b58a0e",
)


def run(command, **kwargs):
    print("COMMAND", json.dumps([str(part) for part in command]), flush=True)
    result = subprocess.run(command, text=True, capture_output=True, **kwargs)
    print(result.stdout, result.stderr, f"EXIT {result.returncode}", flush=True)
    assert result.returncode == 0, command
    return result.stdout


def version(path, supported):
    value = pdf_maker.get_ghostscript_version(str(path))
    print("GHOSTSCRIPT", str(path), value, flush=True)
    assert value and pdf_maker.is_ghostscript_version_supported(value) is supported
    return value


def install_windows(path, evidence):
    import ctypes
    from ctypes import wintypes

    # Upstream .onInit forces SetSilent normal, overriding /S; drive only this process's installer buttons.
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    for name in ["EnumWindows", "EnumChildWindows"]:
        function = getattr(user32, name)
        function.argtypes = ([wintypes.HWND] if name == "EnumChildWindows" else []) + [callback_type, wintypes.LPARAM]
        function.restype = wintypes.BOOL
    for name in ["GetWindowTextW", "GetClassNameW"]:
        getattr(user32, name).argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    for name in ["IsWindowVisible", "IsWindowEnabled"]:
        getattr(user32, name).argtypes = [wintypes.HWND]

    def label(hwnd, function=user32.GetWindowTextW):
        buffer = ctypes.create_unicode_buffer(2048)
        function(hwnd, buffer, len(buffer))
        return buffer.value

    events = []
    command = [str(path), "/S"]
    print("COMMAND", json.dumps(command), "CI button automation; UAC NOT exercised", flush=True)
    with (evidence / f"{path.stem}-installer.log").open("w") as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 300
        previous = None
        while process.poll() is None and time.monotonic() < deadline:
            windows = []

            @callback_type
            def top(hwnd, _):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == process.pid and user32.IsWindowVisible(hwnd) and user32.IsWindowEnabled(hwnd):
                    windows.append(hwnd)
                return True

            user32.EnumWindows(top, 0)
            controls = []
            for window in windows:

                @callback_type
                def child(hwnd, _):
                    if user32.IsWindowVisible(hwnd) and user32.IsWindowEnabled(hwnd):
                        controls.append((hwnd, label(hwnd), label(hwnd, user32.GetClassNameW)))
                    return True

                user32.EnumChildWindows(window, child, 0)
            state = [(text, cls) for _, text, cls in controls]
            if state != previous:
                print("INSTALLER CONTROLS", json.dumps(state), flush=True)
                previous = state
            for hwnd, text, cls in controls:
                if cls == "Button" and text.replace("&", "").strip() in {
                    "Next >",
                    "I Agree",
                    "Install",
                    "Finish",
                    "OK",
                    "No",
                }:
                    print("INSTALLER CLICK", text, flush=True)
                    events.append(text)
                    assert user32.PostMessageW(hwnd, 0x00F5, 0, 0)
                    break
            time.sleep(0.5)
        if process.poll() is None:
            process.kill()
            raise TimeoutError("Verified installer did not finish; inspect INSTALLER CONTROLS")
        print("INSTALLER EXIT", process.returncode, flush=True)
        assert process.returncode == 0
    (evidence / f"{path.stem}-buttons.json").write_text(json.dumps(events), encoding="utf-8")


def install(url, digest, evidence, old=False):
    if sys.platform == "win32" and old:
        # Production download helper is SHA-256; the old publisher supplied SHA-512.
        from urllib.request import urlretrieve

        path = evidence / url.rsplit("/", 1)[1]
        urlretrieve(url, path)
        assert hashlib.sha512(path.read_bytes()).hexdigest() == digest
    else:
        path = Path(autofill._download_ghostscript_installer(url, digest, str(evidence)))
    print("DOWNLOAD", url, "SHA256", hashlib.sha256(path.read_bytes()).hexdigest(), flush=True)
    manifest = evidence / "downloads.json"
    downloads = json.loads(manifest.read_text()) if manifest.exists() else []
    downloads.append({"url": url, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "pinned_digest": digest})
    manifest.write_text(json.dumps(downloads, indent=2), encoding="utf-8")
    if sys.platform == "win32":
        os.environ["GS_ACCEPT_INSTALLER"] = str(path)
        signature = json.loads(
            run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "$s=Get-AuthenticodeSignature -FilePath $env:GS_ACCEPT_INSTALLER; "
                    "[PSCustomObject]@{Status=$s.Status.ToString();Signer=$s.SignerCertificate.Subject;"
                    "Product=(Get-Item $env:GS_ACCEPT_INSTALLER).VersionInfo.ProductName;"
                    "Company=(Get-Item $env:GS_ACCEPT_INSTALLER).VersionInfo.CompanyName} | ConvertTo-Json",
                ]
            )
        )
        assert signature["Status"] == "Valid" and "Artifex Software" in signature["Signer"], signature
        if signature["Product"]:
            assert "ghostscript" in signature["Product"].lower(), signature
        install_windows(path, evidence)
    else:
        signature = run(["/usr/sbin/pkgutil", "--check-signature", str(path)])
        assert "Developer ID Installer: Richard Koch" in signature, signature
        assert "signed by a developer certificate issued by Apple" in signature, signature
        run(["sudo", "/usr/sbin/installer", "-pkg", str(path), "-target", "/"], timeout=300)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["native", "linux-old", "linux-upgraded"])
    args = parser.parse_args()
    assert os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
    evidence = Path(os.environ["RUNNER_TEMP"]) / "gs-upgrade-evidence"
    evidence.mkdir(exist_ok=True)
    print("HOST", platform.platform(), platform.machine(), sys.version, flush=True)
    old_dir = evidence / "old-bin"
    old_dir.mkdir(exist_ok=True)
    original_path = os.environ["PATH"]
    if args.phase == "native":
        assert sys.platform in {"win32", "darwin"}
        if sys.platform == "win32":
            install(OLD_WINDOWS_URL, OLD_WINDOWS_SHA512, evidence, old=True)
            old = Path(os.environ["ProgramFiles"]) / "gs/gs10.04.0/bin/gswin64c.exe"
        else:
            install(*OLD_MACOS, evidence)
            old = Path("/usr/local/bin/gs")
        version(old, False)
        if sys.platform == "darwin":
            # Preserve the actual installed executable before the package replaces it.
            old = Path(shutil.copy2(old, old_dir / "gs"))
        os.environ["PATH"] = str(old.parent) + os.pathsep + original_path
        initial = autofill.get_ghostscript_path()
        assert initial and not pdf_maker.is_ghostscript_version_supported(
            autofill.get_ghostscript_version(initial)
        ), initial
        new_installer = (
            autofill.GHOSTSCRIPT_WINDOWS_INSTALLERS["w64.exe"]
            if sys.platform == "win32"
            else autofill.GHOSTSCRIPT_MACOS_INSTALLER
        )
        # Only the consent/elevation boundary is adapted to unattended hosted CI.
        with patch.object(autofill.click, "confirm", return_value=True) as consent:
            with patch.object(
                autofill, "_install_ghostscript", side_effect=lambda: install(*new_installer, evidence)
            ) as attempt:
                selected = autofill.ensure_ghostscript_available()
            assert attempt.call_count == consent.call_count == 1
        version(old, False)
        expected = "10.08.0" if sys.platform == "win32" else "10.07.1"
        assert expected in version(selected, True)
        (evidence / "old-path.txt").write_text(str(old), encoding="utf-8")
    elif args.phase == "linux-old":
        old = Path("/usr/bin/gs")
        version(old, False)
        assert autofill.get_ghostscript_path() == str(old)
        with patch.object(autofill.click, "confirm", return_value=True) as consent:
            with patch.object(autofill, "_install_ghostscript", wraps=autofill._install_ghostscript) as attempt:
                try:
                    autofill.ensure_ghostscript_available()
                except autofill.click.ClickException as error:
                    assert "Upgrade Ghostscript and check your PATH" in str(error)
                    print("EXPECTED RECOVERY", str(error), flush=True)
                else:
                    raise AssertionError("Apt still supplies an unsupported version; preflight must stop")
            assert attempt.call_count == consent.call_count == 1
        version(old, False)
        (evidence / "old-path.txt").write_text(str(old), encoding="utf-8")
        return
    else:
        old = Path((evidence / "old-path.txt").read_text(encoding="utf-8"))
        os.environ["PATH"] = str(old.parent) + os.pathsep + original_path
        version(old, False)
        selected = autofill.get_ghostscript_path()
        assert selected and "10.08.0" in version(selected, True)
        assert str(Path(os.environ["RUNNER_TEMP"]) / "desktop-ghostscript") in selected
    # Recheck without granting consent: conversion must choose supported GS with old first on PATH.
    assert Path(shutil.which(old.name)).resolve() == old.resolve()
    with patch.object(autofill.click, "confirm", side_effect=AssertionError("Must not prompt after upgrade")):
        assert autofill.ensure_ghostscript_available() == selected
    profile = icc._download_profile()
    assert profile and hashlib.sha256(Path(profile).read_bytes()).hexdigest() == icc.ICC_PROFILE_SHA256
    run([sys.executable, "tests/smoke_pdf_export.py", "--icc-profile", profile], timeout=420)
    result = {
        "old": str(old),
        "old_version": version(old, False),
        "selected": selected,
        "selected_version": version(selected, True),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "profile_sha256": icc.ICC_PROFILE_SHA256,
        "passed": [
            "real old-to-supported installation",
            "old-first PATH",
            "production discovery/preflight",
            "PDF/X conversion",
            "four rasterized faces/dimensions/orientation/edges",
            "embedded profile",
            "cache reuse/rebuild",
        ],
        "manual": ["GUI installer consent", "UAC/password dialogs", "non-admin elevation denial"],
    }
    (evidence / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
