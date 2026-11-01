import automate


class FakeGh:
    def __init__(self, problem=""):
        self.problem, self.secrets, self.variables = problem, {}, {}

    def ready(self):
        return self.problem

    def secret(self, name, value):
        self.secrets[name] = value

    def variable(self, name, value):
        self.variables[name] = value

    def setup_git(self):
        self.git_ready = True


ENV = {
    "GEMINI_API_KEY": "g", "CLOUDFLARE_ACCOUNT_ID": "a", "CLOUDFLARE_API_TOKEN": "c", "VIDEO_SOURCE": "upload",
    "OFFICE_PASSWORD": "pw", "TIKTOK_CLIENT_KEY": "k", "TIKTOK_CLIENT_SECRET": "s", "TIKTOK_REFRESH_TOKEN": "r",
    "INSTAGRAM_USER_ID": "1", "INSTAGRAM_ACCESS_TOKEN": "t",
}  # fmt: skip


def test_keys_become_secrets_and_you_choose_the_runs(capsys):
    gh, saved = FakeGh(), {}
    answers = iter(["", "", "y", "n"])  # TikTok on, not auto; Instagram on, not auto; (X isn't connected)
    assert automate.main(ask=lambda prompt: next(answers), gh=gh, env=ENV, save=lambda k, v: saved.update({k: v})) == 0
    assert saved == {"OFFICE_AUTO_SYNC": "on"} and gh.git_ready
    assert set(gh.secrets) == {"GEMINI_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "TIKTOK_CLIENT_KEY",
                               "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN", "INSTAGRAM_USER_ID", "INSTAGRAM_ACCESS_TOKEN"}  # fmt: skip
    assert "OFFICE_PASSWORD" not in gh.secrets and "VIDEO_SOURCE" not in gh.variables  # local-only settings stay local
    assert gh.variables == {"TIKTOK_AGENT_ENABLED": "true", "TIKTOK_AUTO_APPROVE": "false",
                            "INSTAGRAM_AGENT_ENABLED": "true", "INSTAGRAM_AUTO_APPROVE": "false"}  # fmt: skip
    out = capsys.readouterr().out
    assert "X: not connected yet" in out and "pw" not in out


def test_auto_approve_is_off_unless_you_say_yes():
    gh = FakeGh()
    answers = iter(["y", "y", "y", ""])  # TikTok on + auto; Instagram on, Enter = not auto
    automate.main(ask=lambda prompt: next(answers), gh=gh, env=ENV, save=lambda k, v: None)
    assert gh.variables["TIKTOK_AUTO_APPROVE"] == "true" and gh.variables["INSTAGRAM_AUTO_APPROVE"] == "false"


def test_it_stops_when_gh_isnt_ready_or_there_is_no_ai(capsys):
    assert automate.main(ask=lambda p: "", gh=FakeGh("Log in to GitHub first"), env=ENV) == 1
    gh = FakeGh()
    assert automate.main(ask=lambda p: "", gh=gh, env={"TIKTOK_CLIENT_KEY": "k"}) == 1 and not gh.secrets
    assert "Gemini" in capsys.readouterr().out
