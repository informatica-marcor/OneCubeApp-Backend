"""Isolated upload compatibility tests; repositories and external effects are fakes."""
from dataclasses import replace
from io import BytesIO
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from app.api.routers import users, support_ticket
from app.core.config import settings
from app.utils import uploads


@pytest.fixture
def storage(tmp_path, monkeypatch):
    config = replace(settings, root=str(tmp_path / "app"),
                     uploads_root=str(tmp_path / "volume"),
                     public_base_url="https://app.onecube.cl")
    monkeypatch.setattr(uploads, "settings", config)
    monkeypatch.setattr(users, "settings", config)
    monkeypatch.setattr(users, "DEFAULT_PROFILE_PHOTO",
                        Path(config.root) / "assets" / "default_profile_photo.jpg")
    uploads.get_uploads_root().mkdir()
    # Any unexpected external action fails immediately.
    def forbidden(*args, **kwargs):
        raise AssertionError("External operation forbidden in upload tests")
    for name in ("get_devices", "update_user_face_in_devices",
                 "register_user_in_devices", "register_user_face_in_devices",
                 "delete_user_in_devices", "send_temporary_access_granted_email",
                 "send_portal_access_enabled_email"):
        monkeypatch.setattr(users, name, forbidden)
    return uploads.get_uploads_root()


def make_user(photo):
    return SimpleNamespace(id=7, created_by=3, photo=photo, rut="fixture",
                           name="Fixture", email="fixture@example.com", role="client",
                           company_name=None, company_rut=None)


def write_photo(storage, relative="users/7/photo.jpg"):
    path = storage / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fixture image")
    os.utime(path, (1700000000, 1700000000))
    return path


def test_legacy_and_current_are_same_identity_and_url(storage):
    current = write_photo(storage)
    legacy = "/var/www/onecube/uploads/users/7/photo.jpg"
    assert uploads.resolve_upload_path(legacy) == current.resolve()
    assert users.build_public_file_url(legacy) == users.build_public_file_url(str(current))
    assert users.build_public_file_url(legacy) == "https://app.onecube.cl/uploads/users/7/photo.jpg?v=1700000000"


@pytest.mark.parametrize("prefix", ["", "uploads/", "./uploads/"])
def test_relative_subdirectories_and_url_encoding(storage, prefix):
    relative = "users/7/sub/foto caf\u00e9 #1?.jpg" if os.name != "nt" else "users/7/sub/foto caf\u00e9 #1%.jpg"
    current = write_photo(storage, relative)
    value = prefix + relative
    assert uploads.resolve_upload_path(value) == current.resolve()
    encoded = "users/7/sub/foto%20caf%C3%A9%20%231%3F.jpg" if os.name != "nt" else "users/7/sub/foto%20caf%C3%A9%20%231%25.jpg"
    assert users.build_public_file_url(value) == f"https://app.onecube.cl/uploads/{encoded}?v=1700000000"


def test_fallback_and_previously_persisted_root_relative_path(storage, monkeypatch):
    monkeypatch.setattr(uploads, "settings", replace(uploads.settings, root="app", uploads_root=None))
    assert uploads.get_uploads_root() == (Path.cwd() / "app/uploads").resolve()
    # No file is created in the repository.
    expected = uploads.get_uploads_root() / "users/7/photo.jpg"
    assert uploads.resolve_upload_path("app/uploads/users/7/photo.jpg") == expected
    assert uploads.resolve_upload_path("uploads/users/7/photo.jpg") == expected


@pytest.mark.parametrize("value", [None, 42, [], {}, b"users/7/photo.jpg", "", "\x00",
    "../outside.jpg", "users/../photo.jpg", "uploads/../../outside.jpg",
    "/var/www/onecube/uploads/../outside.jpg", "/var/www/other/uploads/photo.jpg",
    "/var/www/onecube/uploads-other/photo.jpg", "https://example.com/uploads/photo.jpg",
    "file:///tmp/photo.jpg", "//example.com/uploads/photo.jpg", "C:photo.jpg"])
def test_invalid_paths_rejected_without_exposing_input(storage, value):
    with pytest.raises(uploads.InvalidUploadPath, match="^Invalid upload path$"):
        uploads.resolve_upload_path(value)
    assert users.build_public_file_url(value) is None
    users._cleanup_file(value)


def test_outside_absolute_not_read_or_deleted(storage, tmp_path):
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"untouched")
    with pytest.raises(uploads.InvalidUploadPath):
        uploads.resolve_upload_path(outside)
    assert users.build_public_file_url(outside) is None
    users._cleanup_file(str(outside))
    assert outside.read_bytes() == b"untouched"


def test_escape_link_not_read_written_or_deleted(storage, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "photo.jpg"
    target.write_bytes(b"untouched")
    link = storage / "users/7"
    link.parent.mkdir()
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        # Windows directory junctions require no symlink privilege and are
        # also resolved by Path.resolve, exercising the same escape guard.
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                       check=True, capture_output=True)
    for value in (link / "photo.jpg", "users/7/photo.jpg",
                  "/var/www/onecube/uploads/users/7/photo.jpg"):
        with pytest.raises(uploads.InvalidUploadPath):
            uploads.resolve_upload_path(value)
        assert users.build_public_file_url(value) is None
        users._cleanup_file(value)
    with pytest.raises(HTTPException) as error:
        users._save_user_photo(user_id=7, photo=new_upload())
    assert error.value.status_code == 500
    assert target.read_bytes() == b"untouched"


def new_upload():
    return UploadFile(BytesIO(b"new fixture"), filename="photo.jpg",
                      headers=Headers({"content-type": "image/jpeg"}))


def test_new_save_uses_effective_root_and_absolute_persistence(storage):
    saved = users._save_user_photo(user_id=7, photo=new_upload())
    assert Path(saved).is_absolute()
    assert uploads.resolve_upload_path(saved) == storage / "users/7/photo.jpg"
    assert Path(saved).read_bytes() == b"new fixture"
    assert users.build_public_file_url(saved).startswith("https://app.onecube.cl/uploads/users/7/photo.jpg?v=")


@pytest.mark.parametrize("old", ["/var/www/onecube/uploads/users/7/photo.jpg", "users/7/photo.jpg"])
def test_cleanup_preserves_same_file_alias(storage, old):
    saved = users._save_user_photo(user_id=7, photo=new_upload())
    users._cleanup_file(old, keep=saved)
    users._cleanup_file(saved, keep=old)
    assert Path(saved).read_bytes() == b"new fixture"


def test_cleanup_removes_distinct_old_photo_and_handles_default(storage):
    old = write_photo(storage, "users/7/photo.png")
    saved = users._save_user_photo(user_id=7, photo=new_upload())
    users._cleanup_file(str(old), keep=saved)
    assert not old.exists()
    assert Path(saved).exists()
    users._cleanup_file(saved, keep=str(users.DEFAULT_PROFILE_PHOTO))
    assert not Path(saved).exists()


@pytest.fixture
def api(storage, monkeypatch):
    target = make_user("/var/www/onecube/uploads/users/7/missing.jpg")
    monkeypatch.setattr(users.UserRepo, "get_by_id", lambda *args: target)
    monkeypatch.setattr(users.UserRepo, "get_users_clients", lambda *args: [target, make_user(None)])
    app = FastAPI()
    app.include_router(users.router)
    requester = SimpleNamespace(id=1, role="admin")
    app.dependency_overrides[users.get_current_user] = lambda: requester
    app.dependency_overrides[users.get_db] = lambda: None
    with TestClient(app) as client:
        yield client, target, requester, app


def test_missing_photo_keeps_detail_clients_and_temporary_serializer(api):
    client, target, _, _ = api
    response = client.get("/users/7")
    assert response.status_code == 200
    assert response.json()["image"] is None
    response = client.get("/clients")
    assert response.status_code == 200
    assert [row["image"] for row in response.json()] == [None, None]
    assert users.build_temporary_user_out(SimpleNamespace(grantee_user=target, valid_from=None, valid_to=None)).image is None
    response = client.get("/user/7/photo")
    assert response.status_code == 404
    assert response.json() == {"detail": "Photo not found"}


@pytest.mark.parametrize("role,requester_id,allowed", [
    ("admin", 1, True), ("client", 7, True), ("client", 3, True), ("client", 9, False)])
def test_photo_permissions_unchanged(api, storage, role, requester_id, allowed):
    client, target, requester, _ = api
    write_photo(storage)
    target.photo = "/var/www/onecube/uploads/users/7/photo.jpg"
    requester.role, requester.id = role, requester_id
    response = client.get("/user/7/photo")
    assert response.status_code == (200 if allowed else 403)
    if allowed:
        assert response.json() == users.build_public_file_url(target.photo)
    target.photo = "../outside.jpg"
    assert client.get("/user/7/photo").status_code == (404 if allowed else 403)


def test_default_profile_is_not_exposed_or_deleted(api):
    client, target, _, _ = api
    default = users.DEFAULT_PROFILE_PHOTO
    default.parent.mkdir(parents=True)
    default.write_bytes(b"default fixture")
    target.photo = str(default)
    assert client.get("/users/7").json()["image"] is None
    assert client.get("/user/7/photo").status_code == 404
    users._cleanup_file(str(default))
    assert default.read_bytes() == b"default fixture"


def test_db_and_auth_errors_are_not_suppressed(api, monkeypatch):
    client, _, _, app = api
    def broken_db(*args):
        raise RuntimeError("fixture DB failure")
    monkeypatch.setattr(users.UserRepo, "get_by_id", broken_db)
    with pytest.raises(RuntimeError, match="fixture DB failure"):
        client.get("/users/7")
    def denied():
        raise HTTPException(status_code=401, detail="Fixture authentication failed")
    app.dependency_overrides[users.get_current_user] = denied
    assert client.get("/user/7/photo").status_code == 401


@pytest.mark.parametrize("rollback", [False, True])
def test_patch_cleanup_preserves_saved_alias_without_device_operations(storage, monkeypatch, rollback):
    target = make_user("/var/www/onecube/uploads/users/7/photo.jpg")
    # Explicit no-op doubles; no device integration or DB is involved.
    monkeypatch.setattr(users, "get_devices", lambda **kwargs: [])
    monkeypatch.setattr(users, "update_user_face_in_devices", lambda **kwargs: None)
    db = Mock()
    if rollback:
        db.commit.side_effect = RuntimeError("fixture transaction failed")
        with pytest.raises(HTTPException):
            users.update_face(user_id="7", photo=new_upload(), current_user=target, db=db)
    else:
        users.update_face(user_id="7", photo=new_upload(), current_user=target, db=db)
    assert (storage / "users/7/photo.jpg").read_bytes() == b"new fixture"


def test_ticket_url_uses_shared_resolver(storage):
    write_photo(storage, "tickets/1/created/photo.jpg")
    assert support_ticket.build_public_file_url("/var/www/onecube/uploads/tickets/1/created/photo.jpg") == "https://app.onecube.cl/uploads/tickets/1/created/photo.jpg"


def test_summary_keeps_missing_user_and_temporary_photos(api):
    client, target, _, app = api
    permission = SimpleNamespace(grantee_user_id=8, grantee_user=make_user(target.photo),
                                 valid_from=None, valid_to=None)
    permissions = Mock()
    permissions.options.return_value.filter.return_value.order_by.return_value.all.return_value = [permission]
    leases = Mock()
    leases.options.return_value.filter.return_value.order_by.return_value.all.return_value = []
    db = Mock()
    db.query.side_effect = [permissions, leases]
    app.dependency_overrides[users.get_db] = lambda: db
    response = client.get("/user/7/summary")
    assert response.status_code == 200
    assert response.json()["user"]["image"] is None
    assert response.json()["temporary_users"][0]["image"] is None


def test_static_mount_uses_effective_root(storage, monkeypatch):
    import importlib
    from app.core import logging_config
    monkeypatch.setattr(logging_config, "setup_logging", lambda: None)
    main = importlib.import_module("app.main")
    mount = next(route for route in main.app.routes if route.path == "/uploads")
    assert Path(mount.app.directory).resolve() == storage
    write_photo(storage)
    with TestClient(main.app) as client:
        response = client.get("/uploads/users/7/photo.jpg")
    assert response.status_code == 200
    assert response.content == b"fixture image"
