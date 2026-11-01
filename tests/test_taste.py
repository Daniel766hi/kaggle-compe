import taste


def test_no_signals_leaves_the_brief_alone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert taste.with_taste("brief", "tiktok", [{"hook": "a", "status": "draft"}]) == "brief"


def test_notes_approvals_rejections_and_edits_reach_the_brief(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    taste.save_notes("tiktok", "Set the videos in Indonesia.")
    items = [
        {"hook": "Goat inspector", "status": "posted"},
        {"hook": "Cat meeting", "status": "rejected", "reject_reason": "too many cats lately"},
        {"hook": "Duck skater", "status": "approved", "owner_wording": "on screen: First lesson; caption: Send help"},
        {"hook": "Not decided", "status": "draft"},
    ]
    brief = taste.with_taste("brief", "tiktok", items)
    assert brief.startswith("brief\n\n## What the owner likes")
    assert "Set the videos in Indonesia." in brief
    assert "- Goat inspector" in brief and "- Duck skater" in brief and "Not decided" not in brief
    assert "- Cat meeting (why: too many cats lately)" in brief
    assert "on screen: First lesson; caption: Send help" in brief
    assert taste.read_notes("instagram") == ""  # each channel has its own notes
