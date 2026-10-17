"""Download the current Kaggle version and publish the new one.

Auth: set KAGGLE_API_TOKEN (new-style token), or KAGGLE_USERNAME + KAGGLE_KEY (legacy key).
"""

import json
import logging
import os
import tempfile
import time
import zipfile
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
    publish a version built without the previous files (that would erase history).

    Files are downloaded one by one: the all-files zip of a new dataset can stay
    unavailable (404) for a while, single files can't. Right after a new version Kaggle
    can also answer 404 until processing is done, so wait for "ready" and retry.
    """
    wait_until_ready(api, ref)
    files = _list_files(api, ref)
    log.info("Downloading %d files of %s", len(files), ref)
    for name, size in files:
        for attempt in range(1, attempts + 1):
            try:
                api.dataset_download_file(ref, name, path=str(dest), force=True, quiet=True)
                break
            except requests.exceptions.HTTPError as exc:
                if getattr(exc.response, "status_code", None) != 404 or attempt == attempts:
                    raise
                time.sleep(pause_s)
        _unzip_if_needed(Path(dest), name)
        got = (Path(dest) / name).stat().st_size if (Path(dest) / name).exists() else -1
        if size and got != size:
            raise RuntimeError(f"Downloaded {name} is {got} bytes, Kaggle lists {size}; not publishing")


def _list_files(api, ref):
    files, token = [], None
    while True:
        resp = api.dataset_list_files(ref, page_token=token) if token else api.dataset_list_files(ref)
        files += [(f.name, int(f.total_bytes or 0)) for f in (resp.files or [])]
        token = getattr(resp, "nextPageToken", None) or getattr(resp, "next_page_token", None)
        if not token:
            return files


def _unzip_if_needed(dest, name):
    """Kaggle may deliver a large single file as <name>.zip."""
    zipped = dest / f"{name}.zip"
    if zipped.exists() and not (dest / name).exists():
        with zipfile.ZipFile(zipped) as z:
            z.extractall(dest)
        zipped.unlink()


def _check(resp, action):
    error = getattr(resp, "error", None)
    if error:
        raise RuntimeError(f"Kaggle {action} failed: {error}")
    log.info("Kaggle %s ok: %s", action, getattr(resp, "url", ""))


def publish(api, folder, exists, notes, public):
    if exists:
        # A new version *adds* its tags to the dataset's existing ones (max 5 in total), so
        # upload it without tags; update_settings sets the exact list afterwards.
        meta_path = Path(folder) / "dataset-metadata.json"
        original = meta_path.read_text()
        meta_path.write_text(json.dumps({k: v for k, v in json.loads(original).items() if k != "keywords"}))
        try:
            resp = api.dataset_create_version(
                str(folder), notes, quiet=True, convert_to_csv=False, dir_mode="skip"
            )
        finally:
            meta_path.write_text(original)
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

    Kaggle's settings call overwrites visibility, collaborators and license, so these are
    copied from the dataset's current settings: making it public on kaggle.com stays public.

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
    # The settings call only accepts the license under the name Kaggle stored it as
    # (e.g. "Attribution 4.0 International (CC BY 4.0)", not "CC-BY-4.0"); reuse it.
    if current.get("licenses"):
        meta["licenses"] = current["licenses"]
    if current.get("collaborators"):
        meta["collaborators"] = current["collaborators"]
    meta_path.write_text(json.dumps(meta, indent=2))

    for attempt in range(1, attempts + 1):
        try:
            _send_settings(api, ref, folder)
            if cover_is_default(api, ref) and (Path(folder) / "dataset-cover-image.png").exists():
                # Seen in practice: the upload succeeds but the dataset keeps Kaggle's default
                # image (e.g. right after a new version). Applying the settings again fixes it.
                log.warning("Cover image not applied yet; updating settings again")
                time.sleep(30)
                _send_settings(api, ref, folder)
                if cover_is_default(api, ref):
                    log.warning("Cover image still not applied; it will be retried on the next run")
            break
        except SystemExit as exc:  # the client prints the errors and calls exit(1)
            # Right after a version whose file names changed, Kaggle can still answer "doesn't contain a
            # file named ..." for a few minutes; a later attempt goes through. Real errors fail every time.
            if attempt == attempts:
                raise RuntimeError("Kaggle settings update failed (see errors above)") from exc
            log.warning("Kaggle rejected the settings update; retrying in %ds", pause_s)
            time.sleep(pause_s)
        except requests.exceptions.RequestException as exc:
            if attempt == attempts:
                raise
            log.warning("Kaggle settings update failed (%s), retrying", exc)
            time.sleep(pause_s)
    log.info("Kaggle settings updated (private=%s)", meta["isPrivate"])


def _send_settings(api, ref, folder):
    try:
        api.dataset_metadata_update(ref, str(folder))
    except requests.exceptions.JSONDecodeError:
        # Kaggle often answers the settings call with HTTP 200 and an empty body, which the
        # client fails to parse. The settings are applied in that case (checked on the cover).
        log.warning("Kaggle settings call returned an empty reply; treating it as applied")


def cover_is_default(api, ref):
    """True if the dataset still shows Kaggle's placeholder image instead of our cover."""
    owner, slug = ref.split("/")
    try:
        found = [d for d in api.dataset_list(user=owner, search=slug) if d.ref == ref]
    except Exception:  # noqa: BLE001 - a failed check must not fail the run
        return False
    return bool(found) and "default" in (getattr(found[0], "thumbnail_image_url", "") or "")
