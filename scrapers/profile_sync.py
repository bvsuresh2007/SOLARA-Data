"""
Browser profile sync: upload/download persistent Chrome profiles to/from Google Drive.

Usage pattern in each scraper's run() method:

    from scrapers.profile_sync import download_profile, upload_profile

    try:
        download_profile("blinkit")   # before _init_browser()
        self._init_browser()
        ...
    finally:
        self._close_browser()         # must close before zipping
        upload_profile("blinkit")     # upload updated profile

Drive folder: "SolaraDashboard Profiles" (standalone, separate from Reports folder).
Set PROFILE_STORAGE_DRIVE_FOLDER_ID in .env to the folder ID printed by
  python scripts/setup_profiles_drive_folder.py

If PROFILE_STORAGE_DRIVE_FOLDER_ID is not set, all calls are silent no-ops so
local development continues to work without any Drive access.
"""
import logging
import os
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

_FOLDER_ID_ENV = "PROFILE_STORAGE_DRIVE_FOLDER_ID"

# Chromium subdirectories that are safe to skip — caches can be 500 MB+
_SKIP_DIRS = {
    "Cache", "Code Cache", "GPUCache", "DawnCache",
    "ShaderCache", "Service Worker", "CacheStorage",
    "blob_storage", "Session Storage",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _folder_id() -> str | None:
    return os.environ.get(_FOLDER_ID_ENV)


def _get_drive_service():
    try:
        from scrapers.google_drive_upload import _get_drive_service as _gds
    except ImportError:
        from google_drive_upload import _get_drive_service as _gds
    return _gds()


def _zip_profile(profile_dir: Path, zip_path: Path) -> None:
    """Zip profile_dir → zip_path, skipping large cache subdirectories."""
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for item in profile_dir.rglob("*"):
            parts = item.relative_to(profile_dir).parts
            if any(p in _SKIP_DIRS for p in parts):
                continue
            if item.is_file():
                zf.write(item, item.relative_to(profile_dir))
    size_mb = zip_path.stat().st_size / 1_048_576
    logger.info("[ProfileSync] Zipped %s → %s (%.1f MB)", profile_dir.name, zip_path.name, size_mb)


def _drive_upload(service, zip_path: Path, folder_id: str) -> None:
    """Upload zip to Drive folder, replacing any existing file with the same name."""
    from googleapiclient.http import MediaFileUpload
    MIME_ZIP = "application/zip"

    existing = (
        service.files()
        .list(
            q=f"name='{zip_path.name}' and '{folder_id}' in parents and trashed=false",
            fields="files(id)",
        )
        .execute()
        .get("files", [])
    )

    media = MediaFileUpload(str(zip_path), mimetype=MIME_ZIP, resumable=True)

    if existing:
        service.files().update(fileId=existing[0]["id"], media_body=media).execute()
        logger.info("[ProfileSync] Replaced Drive file: %s", zip_path.name)
    else:
        meta = {"name": zip_path.name, "parents": [folder_id]}
        service.files().create(body=meta, media_body=media, fields="id").execute()
        logger.info("[ProfileSync] Uploaded new Drive file: %s", zip_path.name)


def _drive_download(service, zip_name: str, folder_id: str, dest: Path) -> bool:
    """Download zip_name from Drive folder to dest. Returns True if the file existed."""
    import io
    from googleapiclient.http import MediaIoBaseDownload

    results = (
        service.files()
        .list(
            q=f"name='{zip_name}' and '{folder_id}' in parents and trashed=false",
            fields="files(id, name)",
        )
        .execute()
        .get("files", [])
    )

    if not results:
        logger.info("[ProfileSync] %s not found in Drive — will use existing local profile.", zip_name)
        return False

    file_id = results[0]["id"]
    request = service.files().get_media(fileId=file_id)

    with open(dest, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()

    size_mb = dest.stat().st_size / 1_048_576
    logger.info("[ProfileSync] Downloaded %s (%.1f MB)", zip_name, size_mb)
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def download_profile(portal_name: str) -> bool:
    """
    Download <portal_name>_profile.zip from Drive and extract it in place,
    overwriting the existing local profile.

    Call BEFORE launching the browser.

    Returns True if profile was updated from Drive, False if skipped or not found.
    """
    fid = _folder_id()
    if not fid:
        logger.debug("[ProfileSync] PROFILE_STORAGE_DRIVE_FOLDER_ID not set — skipping download.")
        return False

    # Profile lives at scrapers/sessions/<portal>_profile/
    sessions_dir = Path(__file__).resolve().parent / "sessions"
    profile_dir  = sessions_dir / f"{portal_name}_profile"
    zip_path     = sessions_dir / f"{portal_name}_profile.zip"

    try:
        service = _get_drive_service()
        found = _drive_download(service, zip_path.name, fid, zip_path)
        if not found:
            return False

        # Extract — wipe existing profile first so stale files don't linger
        import shutil
        if profile_dir.exists():
            shutil.rmtree(profile_dir)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(profile_dir)

        zip_path.unlink(missing_ok=True)
        logger.info("[ProfileSync] Profile refreshed: %s", profile_dir)
        return True

    except Exception as exc:
        logger.warning("[ProfileSync] download_profile(%s) failed: %s", portal_name, exc)
        zip_path.unlink(missing_ok=True)
        return False


def upload_profile(portal_name: str) -> bool:
    """
    Zip the local <portal_name>_profile directory and upload it to Drive.

    Call AFTER closing the browser — Chrome locks the profile while running.

    Returns True on success, False if skipped or failed (non-fatal).
    """
    fid = _folder_id()
    if not fid:
        logger.debug("[ProfileSync] PROFILE_STORAGE_DRIVE_FOLDER_ID not set — skipping upload.")
        return False

    sessions_dir = Path(__file__).resolve().parent / "sessions"
    profile_dir  = sessions_dir / f"{portal_name}_profile"
    zip_path     = sessions_dir / f"{portal_name}_profile.zip"

    if not profile_dir.exists():
        logger.warning("[ProfileSync] Profile dir not found, cannot upload: %s", profile_dir)
        return False

    try:
        _zip_profile(profile_dir, zip_path)
        service = _get_drive_service()
        _drive_upload(service, zip_path, fid)
        zip_path.unlink(missing_ok=True)
        return True

    except Exception as exc:
        logger.warning("[ProfileSync] upload_profile(%s) failed: %s", portal_name, exc)
        zip_path.unlink(missing_ok=True)
        return False
