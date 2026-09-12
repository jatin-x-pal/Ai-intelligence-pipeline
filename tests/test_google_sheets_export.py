# tests/test_google_sheets_export.py
"""Tests for the Google Sheets export layer.

All external interactions (gspread client, Google credentials) are mocked – no real
network calls are performed.
"""

from __future__ import annotations

import logging
from unittest import mock

import pytest

from src.export.google_sheets import _TAB_HEADERS, GoogleSheetsExporter


# Helper to create a simple mock record with required fields
class DummyRecord:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def model_dump(self, *, by_alias=False, exclude_unset=False):
        # Return the dict directly – the exporter only uses this method.
        return self.__dict__


@pytest.fixture(autouse=True)
def disable_logging_credentials(caplog: pytest.LogCaptureFixture):
    """Ensure that no credential values appear in logs."""
    caplog.set_level(logging.INFO)
    yield
    for record in caplog.records:
        assert "service_account" not in record.getMessage().lower()
        assert "private_key" not in record.getMessage().lower()


def test_configuration_loading(monkeypatch):
    # Settings are loaded from .env – ensure the exporter picks up the values.
    exp = GoogleSheetsExporter()
    assert exp.spreadsheet_id is not None
    assert exp.credentials_path.name == "google-sheets-service-account.json"


def test_worksheet_creation_and_header(monkeypatch):
    # Mock client and spreadsheet chain
    mock_ws = mock.Mock()
    mock_client = mock.Mock()
    mock_spreadsheet = mock.Mock()
    mock_client.open_by_key.return_value = mock_spreadsheet
    # First call to worksheet raises, then returns mock_ws
    mock_spreadsheet.worksheet.side_effect = [Exception("not found"), mock_ws]
    mock_spreadsheet.add_worksheet.return_value = mock_ws
    # row_values returns empty to trigger header creation
    mock_ws.row_values.return_value = []
    mock_ws.col_values.return_value = ["header"]  # dummy existing keys

    with mock.patch("src.export.google_sheets.gspread.authorize", return_value=mock_client), \
         mock.patch("src.export.google_sheets.service_account.Credentials.from_service_account_file"):
        exp = GoogleSheetsExporter()
        import asyncio
        asyncio.run(exp.export({"Startups": []}))
        mock_ws.update.assert_called_once_with("A1", [list(_TAB_HEADERS["Startups"])])

def test_idempotent_export(monkeypatch):
    # Mock worksheet that already contains a source_url
    existing_url = "https://example.com/startup/1"
    mock_ws = mock.Mock()
    mock_ws.row_values.return_value = list(_TAB_HEADERS["Startups"])  # header present
    mock_ws.col_values.return_value = ["source_url", existing_url]
    mock_client = mock.Mock()
    mock_spreadsheet = mock.Mock()
    mock_client.open_by_key.return_value = mock_spreadsheet
    mock_spreadsheet.worksheet.return_value = mock_ws
    with mock.patch("src.export.google_sheets.gspread.authorize", return_value=mock_client), \
         mock.patch("src.export.google_sheets.service_account.Credentials.from_service_account_file"):
        exp = GoogleSheetsExporter()
        rec_new = DummyRecord(source_url="https://example.com/startup/2", source_name="src", collected_at="2024-01-01T00:00:00Z", name="New", description="", website="", founded_date=None)
        rec_dup = DummyRecord(source_url=existing_url, source_name="src", collected_at="2024-01-01T00:00:00Z", name="Dup", description="", website="", founded_date=None)
        import asyncio
        asyncio.run(exp.export({"Startups": [rec_new, rec_dup]}))
        mock_ws.append_rows.assert_called_once()
        args, _ = mock_ws.append_rows.call_args
        rows = args[0]
        assert len(rows) == 1
        assert rows[0][0] == "https://example.com/startup/2"



def test_retry_on_transient_failure(monkeypatch):
    # Simulate a transient failure on worksheet creation, then succeed.
    mock_ws = mock.Mock()
    mock_ws.row_values.return_value = list(_TAB_HEADERS["Jobs"])
    mock_ws.col_values.return_value = ["source_url"]
    mock_spreadsheet = mock.Mock()
    # First call raises, second succeeds.
    mock_spreadsheet.worksheet.side_effect = [Exception("temp failure"), mock_ws]
    # Ensure add_worksheet is not called because we succeed after retry.
    mock_spreadsheet.add_worksheet.return_value = mock_ws

    mock_client = mock.Mock()
    mock_client.open_by_key.return_value = mock_spreadsheet
    with (
        mock.patch("src.export.google_sheets.gspread.authorize", return_value=mock_client),
        mock.patch("src.export.google_sheets.service_account.Credentials.from_service_account_file"),
        mock.patch.object(
            GoogleSheetsExporter,
            "_run_sync",
            side_effect=lambda f, *a, **kw: f(*a, **kw),
        ),
    ):
        exp = GoogleSheetsExporter()
        import asyncio
        asyncio.run(exp.export({"Jobs": []}))

        assert mock_spreadsheet.worksheet.call_count == 2
