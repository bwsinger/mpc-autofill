"""Validate the downloaded final binary on disposable hosted runners; never builds or publishes."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("target", choices=["windows", "macos-arm", "macos-intel", "linux"])
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise RuntimeError("Installer validation requires a disposable GitHub-hosted runner")
    evidence = Path("final-results").resolve()
    evidence.mkdir(exist_ok=True)
    executable = args.executable.resolve()
    executable.chmod(executable.stat().st_mode | 0o111)
    data = executable.read_bytes()
    result = {
        "target": args.target,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "filename": executable.name,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "build_run": 40118782173,
        "build_sha": "a784ac1c70d422dc55e93a1c8ce07e8ee44fa5aa",
        "tag": "dtc-v1.2.6",
        "version": "1.2.6",
        "checks": [],
    }
    if args.target == "windows":
        offset = struct.unpack_from("<I", data, 0x3C)[0]
        assert data[offset : offset + 4] == b"PE\0\0" and struct.unpack_from("<H", data, offset + 4)[0] == 0x8664
        assert platform.machine().lower() in {"amd64", "x86_64"}
        result["architecture"] = "PE x86-64"
    elif args.target.startswith("macos"):
        assert data[:4] == b"\xcf\xfa\xed\xfe"
        expected = 0x100000C if args.target == "macos-arm" else 0x1000007
        assert struct.unpack_from("<I", data, 4)[0] == expected
        assert platform.machine() == ("arm64" if args.target == "macos-arm" else "x86_64")
        result["architecture"] = "Mach-O " + platform.machine()
    else:
        assert data[:6] == b"\x7fELF\x02\x01" and struct.unpack_from("<H", data, 18)[0] == 62
        assert platform.machine() == "x86_64"
        result["architecture"] = "ELF x86-64"
    result["checks"].append("native architecture")
    env = os.environ.copy()
    for name in ["SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"]:
        env.pop(name, None)
    env.update(NO_COLOR="1", PYTHONUTF8="1", XDG_CACHE_HOME=str(Path(os.environ["RUNNER_TEMP"]) / "final-binary-cache"))
    if os.name == "nt":
        import ctypes

        native_cache = ctypes.create_unicode_buffer(32768)
        assert ctypes.windll.shell32.SHGetFolderPathW(None, 28, None, 0, native_cache) == 0
        cache_root = Path(native_cache.value) / "mpc-autofill"
    else:
        cache_root = Path(env["XDG_CACHE_HOME"]) / "mpc-autofill"

    def run(name, command, timeout=180):
        print("COMMAND", json.dumps([str(part) for part in command]), flush=True)
        completed = subprocess.run(command, env=env, capture_output=True, text=True, timeout=timeout)
        output = completed.stdout + completed.stderr
        (evidence / f"{name}.log").write_text(output, encoding="utf-8")
        print(output, "EXIT", completed.returncode, flush=True)
        assert completed.returncode == 0, output
        return output

    try:
        assert run("version", [str(executable), "--version"]).strip() == "MPC Autofill 1.2.6 (bwsinger/mpc-autofill)"
        result["checks"].append("exact release version/repository")
        expected_cache = f"bwsinger-mpc-autofill-40118782173-1-{args.target}-1.2.6"
        cache_names = sorted(path.name for path in cache_root.iterdir() if path.is_dir())
        assert expected_cache in cache_names, cache_names
        result["cache_metadata"] = {"root": str(cache_root), "directories": cache_names, "expected": expected_cache}
        result["checks"].append("original final build cache identity")
        help_output = run("help", [str(executable), "--help"])
        assert "MakePlayingCards" in help_output and "DriveThruCards" in help_output
        result["checks"].append("help")
        assert "TLS check succeeded." in run("tls", [str(executable), "--check-tls"])
        result["checks"].append("TLS without certificate overrides")
        if sys.platform == "win32":
            env["FINAL_BINARY"] = str(executable)
            metadata = json.loads(
                run(
                    "metadata",
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-NonInteractive",
                        "-Command",
                        "$v=(Get-Item $env:FINAL_BINARY).VersionInfo; [PSCustomObject]@{FileVersion=$v.FileVersion;ProductName=$v.ProductName} | ConvertTo-Json",
                    ],
                )
            )
            assert metadata["FileVersion"] in {"1.2.6", "1.2.6.0"}, metadata
            assert metadata["ProductName"] == "bwsinger-mpc-autofill-40118782173-1-windows", metadata
            result["windows_metadata"] = metadata
        # Only these native setup operations import source; every behavior check executes the downloaded binary.
        import accept_ghostscript_upgrade as installer

        from src import icc

        import autofill

        if sys.platform == "win32":
            installer.install(*autofill.GHOSTSCRIPT_WINDOWS_INSTALLERS["w64.exe"], evidence)
            gs = Path(os.environ["ProgramFiles"]) / "gs/gs10.08.0/bin/gswin64c.exe"
        elif sys.platform == "darwin":
            installer.install(*autofill.GHOSTSCRIPT_MACOS_INSTALLER, evidence)
            gs = Path("/usr/local/bin/gs")
        else:
            gs = Path(os.environ["RUNNER_TEMP"]) / "desktop-ghostscript/bin/gs"
        expected_gs = "10.07.1" if sys.platform == "darwin" else "10.08.0"
        assert run("ghostscript-version", [str(gs), "--version"]).strip() == expected_gs
        result["ghostscript"] = {"path": str(gs), "version": expected_gs}
        # The standalone raster checker resolves GS through PATH rather than application imports.
        env["PATH"] = str(gs.parent) + os.pathsep + env["PATH"]
        assert Path(shutil.which(gs.name, path=env["PATH"])).resolve() == gs.resolve()
        profile = icc._download_profile()
        assert profile and hashlib.sha256(Path(profile).read_bytes()).hexdigest() == icc.ICC_PROFILE_SHA256
        result["profile_sha256"] = icc.ICC_PROFILE_SHA256
        run(
            "pdf-default-wakepy",
            [sys.executable, "desktop-tool/tests/smoke_pdf_export.py", str(executable), "--icc-profile", profile],
            timeout=450,
        )
        result["checks"] += [
            "supported real Ghostscript",
            "PDF/X markers",
            "four raster faces/dimensions/orientation/edges",
            "unchanged embedded SWOP",
            "PDF cache reuse/rebuild",
            "default wakepy body without allowsleep",
        ]
        result["status"] = "passed"
    finally:
        result.setdefault("status", "failed")
        (evidence / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
