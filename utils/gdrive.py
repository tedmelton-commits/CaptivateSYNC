"""Google Drive helper functions for the PMC attachment sync app.

Auth note: this uses a plain Google API key (Credentials > API Key in the
Google Cloud Console), NOT a service account. API keys only work against
files/folders that are shared as "Anyone with the link can view" -- they
cannot access private files. Make sure the target Drive folder (and the
images inside it) are set to link-shareable, or every call below will
return an empty list / a 403.
"""
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


def get_drive_service(api_key: str):
    """Build a Drive API client authenticated with a plain API key."""
    return build("drive", "v3", developerKey=api_key, cache_discovery=False)


def list_images_in_folder(service, folder_id: str):
    """Return metadata (id, name, mimeType, modifiedTime) for every image file
    directly inside the given Drive folder. Handles pagination automatically."""
    files = []
    page_token = None
    query = f"'{folder_id}' in parents and trashed = false and mimeType contains 'image/'"
    while True:
        response = (
            service.files()
            .list(
                q=query,
                spaces="drive",
                fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
                pageToken=page_token,
                pageSize=1000,
            )
            .execute()
        )
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return files


def download_file(service, file_id: str) -> bytes:
    """Download a Drive file's raw bytes."""
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()
