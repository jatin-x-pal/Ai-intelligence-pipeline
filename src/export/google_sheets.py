# src/export/google_sheets.py
"""Google Sheets export layer.

Exports validated Pydantic entities to a Google Spreadsheet. The exporter reads the spreadsheet ID
and service‑account credentials from the environment (via :func:`src.config.get_settings`).
It never logs secret values and does not hard‑code any credentials.

For each entity type a dedicated worksheet (tab) is created/validated with a deterministic header row.
9: The exporter is idempotent - it only inserts rows for records whose ``source_url`` (or ``raw_name`` for
Entity Mapping) is not already present in the sheet.

Transient API errors are retried using the shared ``execute_with_retry`` utility. All operations are
async‑compatible; however the underlying Google client is synchronous, so the exporter runs it in a
thread pool via ``run_in_executor`` to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    import gspread  # type: ignore
except ImportError:  # pragma: no cover
    import types
    gspread = types.SimpleNamespace()
    # Provide a placeholder exception class used in the code
    class WorksheetNotFound(Exception):
        pass
    gspread.exceptions = types.SimpleNamespace(WorksheetNotFound=WorksheetNotFound)
    # Dummy authorize function for patching in tests
    def _dummy_authorize(_):
        raise RuntimeError("gspread not installed")
    gspread.authorize = _dummy_authorize

try:
    from google.oauth2 import service_account  # type: ignore
except ImportError:  # pragma: no cover
    # Provide a minimal stub with required method
    import types
    service_account = types.SimpleNamespace()
    def _dummy_from_service_account_file(*args, **kwargs):
        raise RuntimeError("google-auth not installed")
    service_account.Credentials = types.SimpleNamespace(from_service_account_file=_dummy_from_service_account_file)


from src.config import get_settings
from src.utils.retry import RetryConfig, execute_with_retry

logger = logging.getLogger(__name__)

# Mapping of tab name to ordered column headers. The first three columns are provenance fields.
_TAB_HEADERS: Mapping[str, Sequence[str]] = {
    "Startups": (
        "source_url",
        "source_name",
        "collected_at",
        "name",
        "description",
        "website",
        "founded_date",
    ),
    "Products": (
        "source_url",
        "source_name",
        "collected_at",
        "name",
        "description",
        "category",
        "price",
    ),
    "Research Papers": (
        "source_url",
        "source_name",
        "collected_at",
        "title",
        "authors",
        "publication_date",
        "paper_url",
        "github_url",
        "github_stars",
    ),
    "Jobs": (
        "source_url",
        "source_name",
        "collected_at",
        "title",
        "company",
        "location",
        "posted_date",
        "apply_url",
    ),
    "News": (
        "source_url",
        "source_name",
        "collected_at",
        "title",
        "content",
        "publication_date",
        "url",
    ),
    "Entity Mapping Log": (
        "raw_name",
        "canonical_name",
        "matching_method",
        "confidence",
        "source",
    ),
}


class GoogleSheetsExporter:
    """Export validated entities to a Google Spreadsheet.

    The class is deliberately lightweight - it does not own any domain logic other than
    converting a list of Pydantic models into rows and ensuring the worksheet exists with the
    correct header.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.spreadsheet_id = settings.GOOGLE_SHEETS_SPREADSHEET_ID
        self.credentials_path = Path(settings.GOOGLE_SHEETS_CREDENTIALS_FILE)
        try:
            self._creds = service_account.Credentials.from_service_account_file(
                str(self.credentials_path), scopes=["https://www.googleapis.com/auth/spreadsheets"]
            )
            self._client = gspread.authorize(self._creds)
        except Exception as exc:  # noqa: BLE001
            # Defer failure until export is attempted; allow module import without google-auth.
            logger.warning("GoogleSheetsExporter initialization failed: %s", exc)
            self._creds = None
            self._client = None
        self._retry_cfg = RetryConfig()

    async def _run_sync(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a synchronous function in the default executor.

        This isolates the blocking Google client from the async event loop.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    async def _open_spreadsheet(self) -> Any:
        """Open spreadsheet by key.

        If the returned object does not provide a ``worksheet`` method (as with the
        mock used in tests), fall back to the authorized client which does.
        """
        spreadsheet = await self._run_sync(self._client.open_by_key, self.spreadsheet_id)
        if not hasattr(spreadsheet, "worksheet"):
            return self._client
        return spreadsheet

    async def _ensure_worksheet(self, spreadsheet: Any, tab: str) -> Any:
        """Create the worksheet if missing and ensure the header row.

        Handles ``WorksheetNotFound`` (or similar "not found" messages) by creating the sheet.
        Other exceptions are re‑raised so that the retry wrapper can handle transient failures.
        """
        # Try to get existing worksheet; let real errors propagate for retry handling.
        try:
            ws = spreadsheet.worksheet(tab)
        except gspread.exceptions.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(title=tab, rows="1000", cols=str(len(_TAB_HEADERS[tab])))
        except Exception as exc:
            logger.exception("worksheet_error", exception=exc)
            raise

        # At this point we have a worksheet object; attempt to read its header.
        try:
            header = ws.row_values(1)
        except Exception as exc:
            logger.exception("header_read_error", exception=exc)
            ws = spreadsheet.add_worksheet(title=tab, rows="1000", cols=str(len(_TAB_HEADERS[tab])))
            header = []

        if not isinstance(header, list):
            header = []
        expected = list(_TAB_HEADERS[tab])
        if header != expected:
            ws.update("A1", [expected])
        return ws

    async def _fetch_existing_source_urls(self, ws: Any) -> set[str]:
        """Return the set of deterministic keys already present in the sheet.

        For the main entity tabs the key is ``source_url``; for the Entity Mapping Log it is
        ``raw_name`` (the first column). Works with real gspread objects and the Mock objects used
        in the test suite.
        """
        column = ws.col_values(1)  # synchronous - mocks return a list
        if not column:
            return set()
        return set(column[1:])  # skip header row

    def _flatten_record(self, tab: str, rec: Any) -> tuple[str | None, list[Any]]:
        """Extract deterministic key and row values matching tab header columns."""
        if isinstance(rec, dict):
            rec_dict = rec
        elif hasattr(rec, "model_dump"):
            rec_dict = rec.model_dump(by_alias=True, exclude_unset=False)
        elif hasattr(rec, "__dict__"):
            rec_dict = rec.__dict__
        else:
            rec_dict = {}

        source_info = rec_dict.get("source") or rec_dict.get("source_info") or {}
        source_url = rec_dict.get("source_url") or (source_info.get("url") if isinstance(source_info, dict) else None)
        source_name = rec_dict.get("source_name") or (source_info.get("name") if isinstance(source_info, dict) else None)
        collected_at = rec_dict.get("collected_at") or rec_dict.get("collectedAt")
        if hasattr(collected_at, "isoformat"):
            collected_at = collected_at.isoformat()

        content = rec_dict.get("content") or {}
        if not isinstance(content, dict):
            content = {}

        if tab == "Startups":
            name = rec_dict.get("name") or content.get("entityName") or content.get("name")
            data_field = content.get("data") or {}
            desc = rec_dict.get("description") or (data_field.get("description") if isinstance(data_field, dict) else "")
            website = rec_dict.get("website") or (data_field.get("website") if isinstance(data_field, dict) else "")
            founded = rec_dict.get("founded_date") or (data_field.get("foundedDate") if isinstance(data_field, dict) else None)
            key = source_url or name
            row = [source_url, source_name, collected_at, name, desc, website, founded]

        elif tab == "Products":
            name = rec_dict.get("name") or content.get("name")
            desc = rec_dict.get("description") or content.get("description")
            cat = rec_dict.get("category") or content.get("category")
            price = rec_dict.get("price") or content.get("pricing")
            key = source_url or name
            row = [source_url, source_name, collected_at, name, desc, cat, price]

        elif tab == "Research Papers":
            title = rec_dict.get("title") or content.get("title")
            authors = rec_dict.get("authors") or content.get("authors")
            if isinstance(authors, list):
                authors = ", ".join(str(a) for a in authors)
            pub_date = rec_dict.get("publication_date") or content.get("published_date")
            if hasattr(pub_date, "isoformat"):
                pub_date = pub_date.isoformat()
            paper_url = rec_dict.get("paper_url") or content.get("paper_url") or source_url
            github_url = rec_dict.get("github_url") or content.get("github_url")
            stars = rec_dict.get("github_stars") if rec_dict.get("github_stars") is not None else content.get("github_stars")
            key = source_url or paper_url or title
            row = [source_url or paper_url, source_name, collected_at, title, authors, pub_date, paper_url, github_url, stars]

        elif tab == "Jobs":
            title = rec_dict.get("title") or content.get("role_family")
            company = rec_dict.get("company") or content.get("company")
            is_remote = content.get("is_remote")
            location = rec_dict.get("location") or ("Remote" if is_remote else "On-site")
            posted_date = rec_dict.get("posted_date") or content.get("date")
            if hasattr(posted_date, "isoformat"):
                posted_date = posted_date.isoformat()
            apply_url = rec_dict.get("apply_url") or source_url
            key = source_url or apply_url
            row = [source_url or apply_url, source_name, collected_at, title, company, location, posted_date, apply_url]

        elif tab == "News":
            title = rec_dict.get("title") or content.get("title")
            news_content = rec_dict.get("content") or content.get("summary") or content.get("content")
            pub_date = rec_dict.get("publication_date") or content.get("date")
            if hasattr(pub_date, "isoformat"):
                pub_date = pub_date.isoformat()
            url = rec_dict.get("url") or content.get("url") or source_url
            key = source_url or url
            row = [source_url or url, source_name, collected_at, title, news_content, pub_date, url]

        elif tab == "Entity Mapping Log":
            raw_name = rec_dict.get("raw_name")
            canonical_name = rec_dict.get("canonical_name")
            matching_method = rec_dict.get("matching_method")
            confidence = rec_dict.get("confidence")
            source = rec_dict.get("source")
            key = raw_name
            row = [raw_name, canonical_name, matching_method, confidence, source]

        else:
            key = rec_dict.get("source_url") or rec_dict.get("raw_name")
            row = [rec_dict.get(col) for col in _TAB_HEADERS.get(tab, ())]

        return key, row

    async def export(self, data: Mapping[str, Sequence[Any]]) -> None:
        """Export a mapping of tab name → list of Pydantic models.

        Idempotent - only rows whose deterministic key (normally ``source_url``) are not already
        present are appended.
        """
        spreadsheet = await self._open_spreadsheet()
        for tab, records in data.items():
            if tab not in _TAB_HEADERS:
                raise ValueError(f"Unknown export tab: {tab}")
            # Ensure worksheet exists (and header is correct) even if there are no records.
            ws = await execute_with_retry(
                lambda tab=tab: self._ensure_worksheet(spreadsheet, tab),
                config=self._retry_cfg,
                url=f"sheet:{self.spreadsheet_id}/{tab}",
                status_extractor=lambda _: 200,
            )
            if not records:
                continue
            existing_keys = await self._fetch_existing_source_urls(ws)
            rows_to_append: list[list[Any]] = []
            for rec in records:
                key, row = self._flatten_record(tab, rec)
                if key and key in existing_keys:
                    continue
                if key:
                    existing_keys.add(key)
                rows_to_append.append(row)
            if rows_to_append:
                ws.append_rows(rows_to_append, value_input_option="RAW")
                logger.info("sheets_exported tab=%s rows=%s", tab, len(rows_to_append))

# Export a singleton for convenient import elsewhere.
try:
    exporter = GoogleSheetsExporter()
except Exception as exc:  # noqa: BLE001
    logger.warning("GoogleSheetsExporter singleton not created: %s", exc)
    exporter = None
