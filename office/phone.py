"""Open the office on your phone.

`python -m office --phone`: the office also listens on your Wi-Fi, so a phone on the same Wi-Fi
opens it from a link or a QR code. `--anywhere` adds a free Cloudflare quick tunnel (the
`cloudflared` program, no account needed), so the phone can be on mobile data too. Either way
the computer has to stay on, and the office asks for OFFICE_PASSWORD (made for you on first use
and kept in .env); the QR code logs your phone in.
"""

import hashlib
import hmac
import io
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time

import local_env

TUNNEL_URL = re.compile(r"https://[-a-z0-9]+\.trycloudflare\.com")


def password():
    """OFFICE_PASSWORD, made and saved on first use."""
    value = os.environ.get("OFFICE_PASSWORD") or local_env.read().get("OFFICE_PASSWORD") or ""
    if not value:
        value = secrets.token_urlsafe(9)
        local_env.save("OFFICE_PASSWORD", value)
    return value


def login_key(secret):
    """What the phone keeps in its cookie (and what the QR link carries) instead of the password."""
    return hmac.new(secret.encode(), b"ai-office-login", hashlib.sha256).hexdigest()[:32]


def lan_address():
    """This computer's address on the Wi-Fi (no traffic is sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return None


def start_tunnel(port, timeout_s=45, popen=subprocess.Popen):
    """Starts a Cloudflare quick tunnel to the office. Returns (process, public https URL)."""
    exe = shutil.which("cloudflared")
    if not exe:
        raise RuntimeError(
            "cloudflared isn't installed. Windows: winget install --id Cloudflare.cloudflared  "
            "macOS: brew install cloudflared  (then open the office again)"
        )
    proc = popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
                 stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)  # fmt: skip
    found = []

    def read():
        for line in proc.stderr:
            match = TUNNEL_URL.search(line)
            if match and not found:
                found.append(match.group(0))

    threading.Thread(target=read, daemon=True).start()
    deadline = time.monotonic() + timeout_s
    while not found and time.monotonic() < deadline and proc.poll() is None:
        time.sleep(0.2)
    if not found:
        proc.terminate()
        raise RuntimeError("The Cloudflare tunnel didn't start. Check your internet connection and try again.")
    return proc, found[0]


def qr_svg(text):
    import segno

    out = io.BytesIO()
    segno.make(text, error="m").save(out, kind="svg", scale=5, border=2, dark="#111", light="#fff")
    return out.getvalue().decode()


def print_qr(text):
    try:
        import segno

        segno.make(text, error="m").terminal(compact=True)
    except (ImportError, UnicodeError, OSError):  # an old console: the link (and the QR in the page) still work
        pass
