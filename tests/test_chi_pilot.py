"""Offline tests for the chi-pilot χ-Bench agent (everything except live trials)."""

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from chi_pilot import hb_search, kaggle_csv, playbooks, stop_hook
from chi_pilot.domains import CM, PA_PROVIDER, PA_UM, UNKNOWN, detect_domain

REPO = Path(__file__).resolve().parent.parent


# ---------- track detection ----------

@pytest.mark.parametrize(
    "instruction, expected",
    [
        ("| Patient data & provider tools | `chi_bench` MCP server |", PA_PROVIDER),
        ("- Use only payer namespaces: `triage`, `review`", PA_UM),
        ("| Patient data & care-manager tools | `chi_bench` MCP server |", CM),
        ("Call cm_chart.get_chart_data, then cm_outreach.start_outreach_call.", CM),
        ("Use payer_intake_hub.get_intake_case and determination.finalize.", PA_UM),
        ("Use cases.create_from_order then auth.submit_authorization.", PA_PROVIDER),
        ("Summarize this paragraph.", UNKNOWN),
    ],
)
def test_detect_domain(instruction, expected):
    assert detect_domain(instruction) == expected


def test_cm_chart_tool_does_not_count_as_provider_chart_tool():
    assert detect_domain("cm_chart.get_chart_data cm_chart.submit_chart_review") == CM


# ---------- guidance ----------

def test_system_prompt_adds_track_guide_to_core():
    for domain, guide in playbooks.GUIDES.items():
        prompt = playbooks.system_prompt(domain)
        assert prompt.startswith(playbooks.CORE) and guide in prompt
    assert playbooks.system_prompt(UNKNOWN) == playbooks.CORE


def test_audits_are_track_specific():
    assert "payer_letter_center" in playbooks.audit_prompt(PA_UM)
    assert "care plan" in playbooks.audit_prompt(CM).lower()
    assert "forms.validate_form" in playbooks.audit_prompt(PA_PROVIDER)
    assert playbooks.audit_prompt(UNKNOWN).startswith("COMPLETION AUDIT")


# ---------- stop hook ----------

def test_stop_hook_blocks_until_rounds_are_used():
    assert stop_hook.decide(0, 1, "audit") == {"decision": "block", "reason": "audit"}
    assert stop_hook.decide(1, 1, "audit") is None
    assert stop_hook.decide(0, 0, "audit") is None
    assert stop_hook.decide(0, 1, "  ") is None


def _run_hook(state_dir):
    proc = subprocess.run(
        [sys.executable, str(REPO / "chi_pilot" / "stop_hook.py")],
        input='{"stop_hook_active": false}',
        capture_output=True,
        text=True,
        env={"CHI_PILOT_STATE_DIR": str(state_dir)},
        check=True,
    )
    return proc.stdout


def test_stop_hook_script_blocks_once_then_lets_the_agent_stop(tmp_path):
    (tmp_path / "audit.md").write_text("check everything")
    (tmp_path / "audit_max_rounds").write_text("1")
    (tmp_path / "audit_rounds").write_text("0")
    assert json.loads(_run_hook(tmp_path)) == {"decision": "block", "reason": "check everything"}
    assert _run_hook(tmp_path) == ""
    assert (tmp_path / "audit_rounds").read_text() == "1"


def test_stop_hook_without_state_lets_the_agent_stop(tmp_path):
    assert _run_hook(tmp_path / "missing") == ""


# ---------- handbook search ----------

@pytest.fixture
def handbook(tmp_path):
    refs = tmp_path / "references"
    refs.mkdir()
    (refs / "bariatric-surgery.md").write_text(
        "# Bariatric Surgery Policy\n\n## 4.2 Criteria\nBMI of 40 or more.\nSix month diet program.\n"
    )
    (refs / "denial-letters.md").write_text("# Denial Letters\n\nState the rationale and appeal rights.\n")
    (refs / "assessment.md").write_text("# Assessment Standards\n\nScreen with PHQ-9 when PHQ-2 is positive.\n")
    return tmp_path


def test_search_ranks_the_relevant_document_first(handbook):
    index = hb_search.Index(handbook)
    (_, best), *_ = index.search("bmi criteria for bariatric surgery", k=3)
    assert index.paths[best] == "references/bariatric-surgery.md"
    (_, best), *_ = index.search("appeal rights", k=3)
    assert index.paths[best] == "references/denial-letters.md"


def test_search_splits_hyphenated_codes(handbook):
    index = hb_search.Index(handbook)
    (_, best), *_ = index.search("phq", k=1)
    assert index.paths[best] == "references/assessment.md"


def test_search_cli_and_cached_index(handbook, capsys, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(handbook))
    assert hb_search.main(["--root", str(handbook), "diet", "program"]) == 0
    first = capsys.readouterr().out
    assert "bariatric-surgery.md" in first and "Six month diet program." in first
    assert hb_search.main(["--root", str(handbook), "diet", "program"]) == 0  # from the cache
    assert capsys.readouterr().out == first
    assert hb_search.main(["--root", str(handbook), "unmatched-term"]) == 1


# ---------- Kaggle submission file ----------

def _trial(root, name, task, reward, started, reward_file=True):
    trial = root / name
    (trial / "verifier").mkdir(parents=True)
    result = {
        "task_name": task,
        "trial_name": f"{task}__x",
        "started_at": started,
        "verifier_result": {"rewards": {"reward": reward}},
    }
    (trial / "result.json").write_text(json.dumps(result))
    if reward_file:
        (trial / "verifier" / "reward.json").write_text(json.dumps({"reward": reward}))


def _data_root(tmp_path, tasks):
    for rel, names in zip(kaggle_csv.DOMAIN_TASK_DIRS, tasks):
        for name in names:
            (tmp_path / "data" / rel / name).mkdir(parents=True)
    return tmp_path / "data"


def test_kaggle_csv_one_row_per_task_first_attempt_counts(tmp_path):
    data = _data_root(tmp_path, [["pa_1"], ["um_1"], ["cm_1", "cm_2"]])
    trials = tmp_path / "trials"
    _trial(trials / "pa_provider", "t1", "pa_1", 1.0, "2026-10-01T10:00:00")
    _trial(trials / "pa_um", "t2", "um_1", 0.0, "2026-10-01T10:00:00")
    _trial(trials / "pa_um", "t3", "um_1", 1.0, "2026-10-01T11:00:00")  # later attempt
    _trial(trials / "cm", "t4", "cm_1", 1.0, "2026-10-01T10:00:00", reward_file=False)
    (trials / "result.json").write_text(json.dumps({"n_trials": 4}))  # run-level aggregate
    out = tmp_path / "submission.csv"

    assert kaggle_csv.main(["--trials", str(trials), "--data-root", str(data), "--out", str(out)]) == 0
    assert out.read_text().splitlines() == [
        "task_id,reward",
        "cm_1,1",
        "cm_2,0",  # no trial
        "pa_1,1",
        "um_1,0",
    ]


def test_kaggle_csv_requires_all_task_directories(tmp_path):
    with pytest.raises(FileNotFoundError):
        kaggle_csv.public_task_ids(tmp_path)


# ---------- installer ----------

def _installer():
    spec = importlib.util.spec_from_file_location("install_chi_pilot", REPO / "scripts" / "install_chi_pilot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REGISTRY = '''IN_TREE_AGENT_IMPORT_PATHS: dict[str, str] = {
    "openai-agents": "x:Y",
}

AGENT_ENV_VARS: dict[str, tuple[str, ...]] = {
    "openai-agents": ("OPENAI_API_KEY",),
}
'''


def test_installer_copies_package_and_registers_once(tmp_path):
    installer = _installer()
    agents = tmp_path / "src" / "chi_bench" / "experiment" / "agents"
    agents.mkdir(parents=True)
    (agents / "registry.py").write_text(REGISTRY)

    installer.install(tmp_path)
    installer.install(tmp_path)

    registry = (agents / "registry.py").read_text()
    assert registry.count(installer.IMPORT_PATH) == 1
    assert registry.count('"chi-pilot"') == 2  # import path and env hint
    assert (agents / "chi_pilot" / "harness.py").is_file()
    assert not list((agents / "chi_pilot").rglob("__pycache__"))


def test_installer_rejects_unknown_registry_layout():
    with pytest.raises(ValueError):
        _installer().register("AGENTS = {}\n")


# ---------- harness (needs Harbor, which a χ-Bench checkout provides) ----------

def test_harness_trial_files(tmp_path, monkeypatch):
    pytest.importorskip("harbor")
    from chi_pilot import harness

    monkeypatch.setenv("CHI_PILOT_AUDIT_ROUNDS", "2")
    agent = harness.ChiPilotHarness(logs_dir=tmp_path, model_name="anthropic/claude-opus-5-5")
    assert agent._resolved_flags["reasoning_effort"] == "high"
    domain, files = agent._trial_files("- Use only care-manager namespaces: `cm_chart`")
    assert domain == CM
    assert files[f"{harness.STATE_DIR}/audit_max_rounds"] == "2"
    assert playbooks.CM_GUIDE in files[f"{harness.STATE_DIR}/system_prompt.md"]
    settings = json.loads(files[f"{harness.CLAUDE_CONFIG_DIR}/settings.json"])
    assert settings["hooks"]["Stop"][0]["hooks"][0]["command"].endswith("/stop-hook")


def test_write_command_round_trips_awkward_text(tmp_path):
    pytest.importorskip("harbor")
    from chi_pilot.harness import _write_command

    text = "quotes ' \" $HOME `cmd` \\ and\nnewlines\n"
    target = tmp_path / "out.md"
    subprocess.run(["sh", "-c", _write_command(str(target), text)], check=True)
    assert target.read_text() == text
