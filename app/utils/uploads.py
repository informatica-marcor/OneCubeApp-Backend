"""Upload paths are storage identities, never arbitrary filesystem locations."""
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from app.core.config import settings


LEGACY_UPLOADS_PREFIX = "/var/www/onecube/uploads/"


class InvalidUploadPath(ValueError):
    """A stored value does not identify a file within uploads."""


def get_uploads_root() -> Path:
    return Path(settings.uploads_root or Path(settings.root) / "uploads").resolve()


def resolve_upload_path(value: str | Path) -> Path:
    """Accept native absolute paths, upload-relative paths and uploads/... paths.

    Also accept the relative ROOT/uploads/... spelling previously persisted by
    the app, and translate only the explicitly known legacy absolute prefix.
    No existence check is required, so this also validates write destinations.
    """
    if not isinstance(value, (str, Path)) or not str(value) or "\x00" in str(value):
        raise InvalidUploadPath("Invalid upload path")
    raw = str(value)
    root = get_uploads_root()
    try:
        path = Path(raw)
        if ".." in PurePosixPath(raw.replace("\\", "/")).parts:
            raise InvalidUploadPath("Invalid upload path")
        if raw.startswith(LEGACY_UPLOADS_PREFIX):
            path = root / raw[len(LEGACY_UPLOADS_PREFIX):]
        elif not path.is_absolute():
            if ":" in raw or "\\" in raw or raw.startswith("/"):
                raise InvalidUploadPath("Invalid upload path")
            relative_root = Path(settings.root) / "uploads"
            if not relative_root.is_absolute() and path.is_relative_to(relative_root):
                path = root / path.relative_to(relative_root)
            elif path.parts and path.parts[0] == "uploads":
                path = root / Path(*path.parts[1:])
            else:
                path = root / path
        # Reject unknown absolute locations before following any symlink.
        path.relative_to(root)
        resolved = path.resolve()
        resolved.relative_to(root)
        if resolved == root:
            raise InvalidUploadPath("Invalid upload path")
        return resolved
    except (ValueError, OSError, RuntimeError) as exc:
        raise InvalidUploadPath("Invalid upload path") from exc


def public_upload_url(value: str | Path, *, versioned: bool = False) -> str | None:
    """Missing or invalid files do not break a parent resource's serializer."""
    try:
        path = resolve_upload_path(value)
        if not path.is_file():
            return None
        relative = path.relative_to(get_uploads_root()).as_posix()
        version = f"?v={int(path.stat().st_mtime)}" if versioned else ""
        return f"{settings.public_base_url.rstrip('/')}/uploads/{quote(relative, safe='/')}{version}"
    except (InvalidUploadPath, OSError):
        return None
