"""Smartsheet helper functions for the PMC attachment sync app."""
import io
import mimetypes
import smartsheet


def get_client(api_token: str) -> smartsheet.Smartsheet:
    client = smartsheet.Smartsheet(api_token)
    client.errors_as_exceptions(True)
    return client


def get_sheet_with_attachments(client: smartsheet.Smartsheet, sheet_id):
    """Fetch a sheet including each row's existing attachments, so we can
    avoid re-uploading an image that's already attached."""
    return client.Sheets.get_sheet(sheet_id, include=["attachments"])


def find_column_id(sheet, column_name: str):
    """Case-insensitive lookup of a column id by its title."""
    target = column_name.strip().lower()
    for column in sheet.columns:
        if column.title.strip().lower() == target:
            return column.id
    return None


def get_cell_value(row, column_id):
    for cell in row.cells:
        if cell.column_id == column_id:
            if cell.value is None:
                return None
            return str(cell.value).strip()
    return None


def existing_attachment_names(client, sheet_id, row):
    """Return the set of file names already attached to a row."""
    names = set()
    attachments = getattr(row, "attachments", None) or []
    for att in attachments:
        if getattr(att, "name", None):
            names.add(att.name.strip().lower())
    return names


def attach_file_to_row(client, sheet_id, row_id, filename, file_bytes, mime_type=None):
    if mime_type is None:
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return client.Attachments.attach_file_to_row(
        sheet_id,
        row_id,
        (filename, io.BytesIO(file_bytes), mime_type),
    )
