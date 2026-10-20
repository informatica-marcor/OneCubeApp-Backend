"""Run local checks with synthetic settings, without loading the local .env.

Usage (repository root): python app/tests/run_upload_path_checks.py
Optional pytest targets/arguments may be supplied after the script name.
"""
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import dotenv
import pytest


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    # Block .env even with dotenv versions predating PYTHON_DOTENV_DISABLED.
    dotenv.load_dotenv = lambda *args, **kwargs: None
    with TemporaryDirectory(prefix="onecube-upload-checks-") as directory:
        os.environ.update(
            PYTHON_DOTENV_DISABLED="1", DATABASE_URL="sqlite://",
            ENCRYPTION_KEY="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
            SECRET_KEY="synthetic-upload-tests-only",
            ROOT=directory, UPLOADS_ROOT=str(Path(directory) / "uploads"),
            PUBLIC_BASE_URL="https://app.onecube.cl",
            RESEND_API_KEY="", EMAIL_ADDRESS="",
        )
        return pytest.main(sys.argv[1:] or ["-q", "-p", "no:cacheprovider", "app/tests"])


if __name__ == "__main__":
    raise SystemExit(main())
