"""Validates that /auth/register creates user folders under the configured Dropbox base folder.

This script:
- Posts a synthetic registration payload to /auth/register using Flask test_client.
- Verifies the expected folder exists in Dropbox at with_base_folder(f"/{email}").
- Cleans up the created Dropbox folder and DB rows afterwards.

Safe to run multiple times: it generates a unique email each run.

Usage:
  venv/bin/python scripts/validate_register_dropbox.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
import secrets

# Ensure project root is on sys.path even when running from outside the repo cwd.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app, db
from app.dropbox_utils import get_dropbox_base_folder, get_dropbox_client, with_base_folder
from app.models import Folder, User, UserActivityLog


def main() -> int:
    app = create_app()

    email = f"test.dropbox+{uuid.uuid4().hex[:8]}@example.com"
    phone_suffix = f"{secrets.randbelow(1000000):06d}"

    form_data = {
        "name": "Test",
        "lastname": "Dropbox",
        "email": email,
        "telephone": f"+1 555 {phone_suffix}",
        "zip_code": "12345",
        "city": "Bogota",
        "state": "Cundinamarca",
        "address": "Calle 1 #2-3",
        "document_type": "cedula",
        "document_number": f"TST-{uuid.uuid4().hex[:6].upper()}",
        "nationality": "Colombiana",
        "country": "CO",
        "date_of_birth": "1990-01-01",
        "password": "Passw0rd!",
        "confirm_password": "Passw0rd!",
        # WTForms BooleanField expects presence of the key
        "communications": "y",
    }

    with app.app_context():
        db.create_all()

        client = app.test_client()
        resp = client.post("/auth/register", data=form_data, follow_redirects=True)

        print(f"HTTP status: {resp.status_code}")

        user = User.query.filter_by(email=email).first()
        print(f"User created: {bool(user)} | id: {getattr(user, 'id', None)}")
        if not user:
            print("Registration did not create a user; cannot validate Dropbox folder.")
            try:
                text = (resp.data or b"")[:4000].decode("utf-8", errors="replace")
                print("--- Response excerpt (first 4000 bytes) ---")
                print(text)
                print("--- End excerpt ---")
            except Exception as e:
                print(f"Could not decode response body for debugging: {e}")

            # Re-run WTForms validation in an explicit request context to get exact field errors.
            try:
                from forms import ClienteRegistrationForm
                from app.utils.countries import get_countries_list, get_nationalities_list

                with app.test_request_context("/auth/register", method="POST", data=form_data):
                    form = ClienteRegistrationForm()
                    countries = get_countries_list()
                    nationalities = get_nationalities_list()
                    form.nationality.choices = [("", "Selecciona tu nacionalidad")] + nationalities  # type: ignore[assignment]
                    form.country.choices = [("", "Selecciona tu país")] + [
                        (code, country) for code, country in countries
                    ]  # type: ignore[assignment]
                    ok = form.validate()
                    print("WTForms validate() ok:", ok)
                    print("WTForms errors:", form.errors)
            except Exception as e:
                print(f"Could not reproduce WTForms validation errors: {e}")

            return 2

        rel_path = f"/{email}"
        base = get_dropbox_base_folder()
        full_path = with_base_folder(rel_path)
        print(f"Configured base: {base}")
        print(f"Expected Dropbox folder: {full_path}")

        dbx = get_dropbox_client()
        if not dbx:
            print("No Dropbox client available (token/config issue).")
            return 3

        # Verify folder exists
        md = dbx.files_get_metadata(full_path)
        print(f"Dropbox metadata name: {getattr(md, 'name', None)}")

        # Cleanup: delete Dropbox folder
        try:
            dbx.files_delete_v2(full_path)
            print("Cleanup: deleted Dropbox folder")
        except Exception as e:
            print(f"Cleanup: could not delete Dropbox folder: {e}")

        # Cleanup: delete DB rows
        try:
            # Delete dependent rows first to satisfy FK constraints.
            UserActivityLog.query.filter_by(user_id=user.id).delete()
            Folder.query.filter_by(user_id=user.id).delete()
            db.session.delete(user)
            db.session.commit()
            print("Cleanup: deleted DB user + folders")
        except Exception as e:
            db.session.rollback()
            print(f"Cleanup: could not delete DB rows: {e}")

    print("OK: /auth/register created Dropbox folder under base.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
