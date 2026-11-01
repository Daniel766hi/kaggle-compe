"""Turn on the daily automation: GitHub runs the agents every day, even with your computer off.

    python -m automate          # Windows: double-click automate.cmd

It copies the keys you saved in .env (by the setup script and the login commands) into your
repository's encrypted GitHub secrets, then asks which daily runs to turn on. It uses the GitHub
command-line tool `gh` (Windows: winget install --id GitHub.cli), logged in with `gh auth login`.
Nothing is sent anywhere but GitHub, and secrets are never printed.

What the runs do (times in WIB):
  TikTok     09:37  plans videos when fewer than 3 are waiting, then makes the oldest approved
                    one and sends it to your TikTok inbox (you post it from the app)
  Instagram  18:07  the same, then publishes the oldest approved Reel (it goes live)
  X          07:17 and 18:47  drafts posts, then posts the oldest approved one (X charges per post)

Approving stays with you unless you choose otherwise: approve in the office (from your phone too);
the office syncs with GitHub by itself, so the next run picks it up.
"""

import shutil
import subprocess
import sys

import local_env

BRAIN = ("GEMINI_API_KEY", "ANTHROPIC_API_KEY")
VISUALS = ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "DASHSCOPE_API_KEY", "PIXABAY_API_KEY", "PEXELS_API_KEY")
RUNS = {
    "TIKTOK": {
        "name": "TikTok",
        "when": "every day at 09:37 WIB",
        "keys": ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"),
        "login": "python -m tiktok_agent login",
        "auto": "Videos still land in your TikTok inbox as drafts; you post them from the app.",
    },
    "INSTAGRAM": {
        "name": "Instagram",
        "when": "every day at 18:07 WIB",
        "keys": ("INSTAGRAM_USER_ID", "INSTAGRAM_ACCESS_TOKEN"),
        "login": "python -m instagram_agent login",
        "auto": "Reels go LIVE on your account with nobody looking at them first.",
    },
    "X": {
        "name": "X",
        "when": "twice a day, 07:17 and 18:47 WIB",
        "keys": ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"),
        "login": "python -m x_agent login",
        "auto": "Posts go LIVE on your X account (and X charges for each) with nobody looking at them first.",
    },
}


class Gh:
    """The few `gh` calls this needs. Secret values go in through stdin, never the command line."""

    def __init__(self, run=subprocess.run):
        self.run = run

    def ready(self):
        if not shutil.which("gh"):
            return "GitHub's command-line tool isn't installed. Windows: winget install --id GitHub.cli  (then reopen this window)"
        if self.run(["gh", "auth", "status"], capture_output=True, text=True).returncode:
            return "Log in to GitHub first: gh auth login   (choose GitHub.com, HTTPS, and log in with a web browser)"
        return ""

    def secret(self, name, value):
        result = self.run(["gh", "secret", "set", name], input=value, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"Couldn't save {name}: {result.stderr.strip()[:200]}")

    def setup_git(self):
        """Let git use gh's login, so the office can sync with GitHub without asking."""
        self.run(["gh", "auth", "setup-git"], capture_output=True, text=True)

    def variable(self, name, value):
        result = self.run(["gh", "variable", "set", name, "--body", value], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"Couldn't set {name}: {result.stderr.strip()[:200]}")


def main(argv=None, ask=input, gh=None, env=None, save=local_env.save):
    print("Turning on the daily automation (GitHub runs the agents every day, even with your computer off).\n")
    gh = gh or Gh()
    problem = gh.ready()
    if problem:
        print(problem)
        return 1
    env = local_env.read() if env is None else env

    if not any(env.get(k) for k in BRAIN):
        print("No AI key in .env yet. Run the setup script and add your free Gemini key first.")
        return 1
    copied = []
    for name in (*BRAIN, *VISUALS, *(k for run in RUNS.values() for k in run["keys"])):
        if env.get(name):
            gh.secret(name, env[name])
            copied.append(name)
    print(f"Saved {len(copied)} keys as encrypted GitHub secrets: {', '.join(copied)}\n")
    if not any(env.get(k) for k in VISUALS[:2] + VISUALS[3:]):
        print("Note: no Cloudflare or Pixabay key, so the daily runs can plan videos but not make them.\n")

    turned_on = []
    for prefix, run in RUNS.items():
        if not all(env.get(k) for k in run["keys"]):
            print(f"{run['name']}: not connected yet, skipped (run `{run['login']}` first, then this again).")
            continue
        if not _yes(ask, f"Run {run['name']} {run['when']}? [Y/n] ", default=True):
            gh.variable(f"{prefix}_AGENT_ENABLED", "false")
            print(f"  {run['name']}: off.")
            continue
        gh.variable(f"{prefix}_AGENT_ENABLED", "true")
        auto = _yes(
            ask,
            f"  Also approve {run['name']} plans by itself, without asking you? {run['auto']} "
            "(Plans with something to fact-check always wait for you.) [y/N] ",
            default=False,
        )
        gh.variable(f"{prefix}_AUTO_APPROVE", "true" if auto else "false")
        turned_on.append(f"{run['name']} ({'fully automatic' if auto else 'you approve, it does the rest'})")

    if turned_on:
        gh.setup_git()
        save("OFFICE_AUTO_SYNC", "on")
        print("\nDaily runs on: " + "; ".join(turned_on) + ".")
        print("Watch them in your repository on GitHub: Actions tab. Run this again any time to change your choices.")
        print("While the office is open it now syncs with GitHub by itself, so what you approve reaches the next run")
        print("and finished videos come back to the office. Restart the office once to start that.")
    else:
        save("OFFICE_AUTO_SYNC", "off")
        print("\nNo daily runs turned on.")
    return 0


def _yes(ask, prompt, default):
    answer = ask(prompt).strip().lower()
    return default if not answer else answer in ("y", "yes", "ya")


if __name__ == "__main__":
    sys.exit(main())
