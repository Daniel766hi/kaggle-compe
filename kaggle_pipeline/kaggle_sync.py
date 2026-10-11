"""Download the current Kaggle version and publish the new one.

Auth: set KAGGLE_API_TOKEN (new-style token), or KAGGLE_USERNAME + KAGGLE_KEY (legacy key).
"""

import json
import logging
import os
import tempfile
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)


def get_api():
    # GitHub Actions sets unset secrets to "", which the Kaggle client would read as
    # an (empty) credential and try before the one that is actually set.
    for key in [k for k, v in os.environ.items() if k.startswith("KAGGLE_") and not v]:
        del os.environ[key]
    from kaggle.api.kaggle_api_extended import KaggleApi  # imported lazily: dry runs need no credentials

    api = KaggleApi()
    api.authenticate()
    return api


def dataset_exists(api, ref):
    try:
        api.dataset_status(ref)
        return True
    except requests.exceptions.HTTPError as exc:
        # Kaggle answers 403 PERMISSION_DENIED (not 404) for a dataset that doesn't exist yet.
        # If it does exist and we lack access, the create call fails loudly, so nothing is lost.
        if getattr(exc.response, "status_code", None) in (403, 404):
            return False
        raise


def download_current(api, ref, dest, attempts=4, pause_s=30):
    """Fetch every file of the current version. Any failure aborts the run, so we never
    publish a version built without the previous panels (that would erase history).

    Right after a new version, Kaggle can answer 404 until it has finished processing,
    so wait for "ready" and retry a few times.
    """
    wait_until_ready(api, ref)
    for attempt in range(1, attempts + 1):
        log.info("Downloading current version of %s (attempt %d)", ref, attempt)
        try:
            api.dataset_download_files(ref, path=str(dest), force=True, quiet=True, unzip=True)
            return
        except requests.exceptions.HTTPError as exc:
            if getattr(exc.response, "status_code", None) != 404 or attempt == attempts:
                raise
            time.sleep(pause_s)


def _check(resp, action):
    error = getattr(resp, "error", None)
    if error:
        raise RuntimeError(f"Kaggle {action} failed: {error}")
    log.info("Kaggle %s ok: %s", action, getattr(resp, "url", ""))


def publish(api, folder, exists, notes, public):
    if exists:
        resp = api.dataset_create_version(
            str(folder), notes, quiet=True, convert_to_csv=False, dir_mode="skip"
        )
        _check(resp, "new version")
    else:
        resp = api.dataset_create_new(
            str(folder), public=public, quiet=True, convert_to_csv=False, dir_mode="skip"
        )
        _check(resp, "create")


def wait_until_ready(api, ref, timeout_s=600, poll_s=15):
    """A new version is processed asynchronously; settings can only be updated afterwards."""
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            status = api.dataset_status(ref)
        except requests.exceptions.HTTPError as exc:
            # A just-created dataset answers 403/404 for a short while.
            if getattr(exc.response, "status_code", None) not in (403, 404):
                raise
            status = "not visible yet"
        if status == "ready":
            return
        if status == "error" or time.monotonic() > deadline:
            raise RuntimeError(f"Kaggle dataset {ref} is '{status}', not ready")
        time.sleep(poll_s)


def update_settings(api, folder, ref, attempts=3, pause_s=60):
    """Apply what a version upload doesn't: file and column descriptions, sources,
    update frequency and cover image (all read from the folder's dataset-metadata.json).

    Kaggle's settings call overwrites visibility and collaborators, so both are copied
    from the dataset's current settings: making it public on kaggle.com stays public.

    Kaggle's usability score counts sources, update frequency and descriptions when it
    processes a version, so they show up from the version after the first settings update.
    """
    with tempfile.TemporaryDirectory() as tmp:
        current = json.loads(Path(api.dataset_metadata(ref, tmp)).read_text())
    current = current.get("info") or current

    meta_path = Path(folder) / "dataset-metadata.json"
    meta = json.loads(meta_path.read_text())
    # Kaggle omits false booleans from this response, so a missing flag means public.
    meta["isPrivate"] = bool(current.get("isPrivate", False))
    if current.get("collaborators"):
        meta["collaborators"] = current["collaborators"]
    meta_path.write_text(json.dumps(meta, indent=2))

    for attempt in range(1, attempts + 1):
        try:
            api.dataset_metadata_update(ref, str(folder))
            break
        except SystemExit as exc:  # the client prints the errors and calls exit(1)
            raise RuntimeError("Kaggle settings update failed (see errors above)") from exc
        except requests.exceptions.RequestException as exc:
            # Kaggle occasionally answers with an empty body; a retry goes through.
            if attempt == attempts:
                raise
            log.warning("Kaggle settings update failed (%s), retrying", exc)
            time.sleep(pause_s)
    log.info("Kaggle settings updated (private=%s)", meta["isPrivate"])
