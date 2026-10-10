"""Download the current Kaggle version and publish the new one.

Auth: set KAGGLE_API_TOKEN (new-style token), or KAGGLE_USERNAME + KAGGLE_KEY (legacy key).
"""

import logging
import os

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


def download_current(api, ref, dest):
    """Fetch every file of the current version. Any failure aborts the run, so we never
    publish a version built without the previous panels (that would erase history)."""
    log.info("Downloading current version of %s", ref)
    api.dataset_download_files(ref, path=str(dest), force=True, quiet=True, unzip=True)


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
