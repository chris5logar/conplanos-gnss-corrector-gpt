from __future__ import annotations

import io
from typing import Any

import streamlit as st


FOLDER_NAME = "CONPLANOS GNSS - CERTIFICADOS"


def _get_config():
    try:
        account = st.secrets.get("gcp_service_account")
        folder_id = st.secrets.get("GOOGLE_DRIVE_FOLDER_ID", "")
        return account, str(folder_id or "").strip()
    except Exception:
        return None, ""


def configured() -> bool:
    account, _ = _get_config()
    return bool(account)


def _service():
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    account, _ = _get_config()
    if not account:
        raise RuntimeError("Google Drive no está configurado: falta [gcp_service_account].")
    scopes = ["https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(dict(account), scopes=scopes)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _ensure_folder(service):
    _, configured_folder_id = _get_config()
    if configured_folder_id:
        try:
            item = service.files().get(fileId=configured_folder_id, fields="id,name,mimeType").execute()
            if item.get("mimeType") != "application/vnd.google-apps.folder":
                raise RuntimeError("GOOGLE_DRIVE_FOLDER_ID no corresponde a una carpeta de Google Drive.")
            return item["id"]
        except Exception as exc:
            raise RuntimeError(f"No se pudo acceder a GOOGLE_DRIVE_FOLDER_ID: {exc}") from exc

    query = (
        "name = '" + FOLDER_NAME.replace("'", "\\'") + "' "
        "and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    found = service.files().list(q=query, spaces="drive", fields="files(id,name)", pageSize=10).execute().get("files", [])
    if found:
        return found[0]["id"]

    metadata = {"name": FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"}
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def upload_bytes(data: bytes, filename: str, mimetype: str) -> dict[str, str]:
    """Upload a file to the CONPLANOS Drive folder and return id/name/view URL."""
    from googleapiclient.http import MediaIoBaseUpload

    service = _service()
    folder_id = _ensure_folder(service)
    metadata: dict[str, Any] = {"name": filename, "parents": [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mimetype, resumable=False)
    item = service.files().create(body=metadata, media_body=media, fields="id,name,webViewLink").execute()
    file_id = item["id"]
    view_link = item.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"
    return {"id": file_id, "name": item.get("name", filename), "url": view_link}
