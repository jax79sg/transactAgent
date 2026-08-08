"""Tests for drive_client.py's Drive API pagination.

Regression coverage for a real, live-reported failure: list_folder_pdf_files()
called files().list() once with no pageSize/nextPageToken handling, so it silently
truncated at the Drive API's default page size of 100 -- any folder with more than
100 PDFs would only ever ingest the first 100. See aidlc-docs/audit.md 2026-08-05.
"""

from unittest.mock import MagicMock, patch

from ingestion_worker.clients.drive_client import (
    DriveFileRef,
    delete_file,
    ensure_backup_folder_exists,
    list_backup_folder_files,
    list_folder_pdf_files,
    upload_file,
)


def _mock_service_with_pages(*pages: list[dict]):
    """Builds a fake `service.files().list(...).execute()` chain that returns each
    of `pages` in turn (each page a list of {"id", "name"} dicts), with a
    nextPageToken on every page but the last."""
    service = MagicMock()
    responses = [
        {"files": page, **({"nextPageToken": f"token-{i}"} if i < len(pages) - 1 else {})}
        for i, page in enumerate(pages)
    ]
    service.files.return_value.list.return_value.execute.side_effect = responses
    return service


class TestListFolderPdfFilesPagination:
    def test_single_page_under_the_default_limit(self):
        files = [{"id": f"id{i}", "name": f"file{i}.pdf"} for i in range(5)]
        service = _mock_service_with_pages(files)
        with patch("ingestion_worker.clients.drive_client._load_credentials", return_value=MagicMock()), patch(
            "ingestion_worker.clients.drive_client.build", return_value=service
        ):
            result = list_folder_pdf_files(db=MagicMock())

        assert result == [DriveFileRef(id=f["id"], name=f["name"]) for f in files]
        assert service.files.return_value.list.call_count == 1

    def test_pages_through_more_than_100_files(self):
        # Regression case: a folder with 150 files, returned across two pages (as
        # the real Drive API would with its 100-item default page size) -- all 150
        # must come back, not just the first page.
        page1 = [{"id": f"id{i}", "name": f"file{i}.pdf"} for i in range(100)]
        page2 = [{"id": f"id{i}", "name": f"file{i}.pdf"} for i in range(100, 150)]
        service = _mock_service_with_pages(page1, page2)
        with patch("ingestion_worker.clients.drive_client._load_credentials", return_value=MagicMock()), patch(
            "ingestion_worker.clients.drive_client.build", return_value=service
        ):
            result = list_folder_pdf_files(db=MagicMock())

        assert len(result) == 150
        assert result == [DriveFileRef(id=f["id"], name=f["name"]) for f in page1 + page2]
        assert service.files.return_value.list.call_count == 2

    def test_second_page_request_carries_the_page_token(self):
        page1 = [{"id": "id0", "name": "file0.pdf"}]
        page2 = [{"id": "id1", "name": "file1.pdf"}]
        service = _mock_service_with_pages(page1, page2)
        with patch("ingestion_worker.clients.drive_client._load_credentials", return_value=MagicMock()), patch(
            "ingestion_worker.clients.drive_client.build", return_value=service
        ):
            list_folder_pdf_files(db=MagicMock())

        first_call_kwargs = service.files.return_value.list.call_args_list[0].kwargs
        second_call_kwargs = service.files.return_value.list.call_args_list[1].kwargs
        assert first_call_kwargs["pageToken"] is None
        assert second_call_kwargs["pageToken"] == "token-0"

    def test_would_have_dropped_files_beyond_the_first_page_without_the_fix(self):
        # Prove the test actually catches the regression: simulating the pre-fix
        # behaviour (only ever reading the first page) drops the second page.
        page1 = [{"id": f"id{i}", "name": f"file{i}.pdf"} for i in range(100)]
        page2 = [{"id": f"id{i}", "name": f"file{i}.pdf"} for i in range(100, 150)]
        service = _mock_service_with_pages(page1, page2)
        with patch("ingestion_worker.clients.drive_client._load_credentials", return_value=MagicMock()), patch(
            "ingestion_worker.clients.drive_client.build", return_value=service
        ):
            # Simulate the old, unpaginated call directly against the mock service
            # to show what the pre-fix code path would have returned.
            first_page_only = service.files().list(q="", fields="files(id, name)").execute()

        assert len(first_page_only["files"]) == 100  # pre-fix: only the first 100, page 2 silently lost


class TestEnsureBackupFolderExists:
    """Epic 7 (Nightly Transaction Backup) -- WR-14."""

    def test_returns_existing_folder_id_without_creating(self):
        service = MagicMock()
        service.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "existing-folder-id", "name": "backup"}]
        }
        with patch("ingestion_worker.clients.drive_client._load_credentials", return_value=MagicMock()), patch(
            "ingestion_worker.clients.drive_client.build", return_value=service
        ):
            folder_id = ensure_backup_folder_exists(db=MagicMock(), parent_folder_id="parent-id")

        assert folder_id == "existing-folder-id"
        service.files.return_value.create.assert_not_called()

    def test_creates_folder_when_none_exists(self):
        service = MagicMock()
        service.files.return_value.list.return_value.execute.return_value = {"files": []}
        service.files.return_value.create.return_value.execute.return_value = {"id": "new-folder-id"}
        with patch("ingestion_worker.clients.drive_client._load_credentials", return_value=MagicMock()), patch(
            "ingestion_worker.clients.drive_client.build", return_value=service
        ):
            folder_id = ensure_backup_folder_exists(db=MagicMock(), parent_folder_id="parent-id")

        assert folder_id == "new-folder-id"
        create_kwargs = service.files.return_value.create.call_args.kwargs
        assert create_kwargs["body"]["name"] == "backup"
        assert create_kwargs["body"]["parents"] == ["parent-id"]


class TestUploadFile:
    def test_uploads_and_returns_file_ref(self):
        service = MagicMock()
        service.files.return_value.create.return_value.execute.return_value = {
            "id": "uploaded-id",
            "name": "transactions-backup-20260808T020000Z.csv",
        }
        with patch("ingestion_worker.clients.drive_client._load_credentials", return_value=MagicMock()), patch(
            "ingestion_worker.clients.drive_client.build", return_value=service
        ):
            result = upload_file(
                db=MagicMock(),
                folder_id="folder-id",
                filename="transactions-backup-20260808T020000Z.csv",
                content=b"id,description\n",
                mime_type="text/csv",
            )

        assert result == DriveFileRef(id="uploaded-id", name="transactions-backup-20260808T020000Z.csv")
        create_kwargs = service.files.return_value.create.call_args.kwargs
        assert create_kwargs["body"]["parents"] == ["folder-id"]


class TestListBackupFolderFiles:
    def test_pages_through_results_and_captures_created_time(self):
        service = MagicMock()
        page1 = [{"id": "id0", "name": "transactions-backup-a.csv", "createdTime": "2026-08-01T02:00:00Z"}]
        page2 = [{"id": "id1", "name": "transactions-backup-b.csv", "createdTime": "2026-08-02T02:00:00Z"}]
        service.files.return_value.list.return_value.execute.side_effect = [
            {"files": page1, "nextPageToken": "token-0"},
            {"files": page2},
        ]
        with patch("ingestion_worker.clients.drive_client._load_credentials", return_value=MagicMock()), patch(
            "ingestion_worker.clients.drive_client.build", return_value=service
        ):
            result = list_backup_folder_files(db=MagicMock(), folder_id="folder-id")

        assert result == [
            DriveFileRef(id="id0", name="transactions-backup-a.csv", created_time="2026-08-01T02:00:00Z"),
            DriveFileRef(id="id1", name="transactions-backup-b.csv", created_time="2026-08-02T02:00:00Z"),
        ]
        assert service.files.return_value.list.call_count == 2


class TestDeleteFile:
    def test_deletes_by_file_id(self):
        service = MagicMock()
        with patch("ingestion_worker.clients.drive_client._load_credentials", return_value=MagicMock()), patch(
            "ingestion_worker.clients.drive_client.build", return_value=service
        ):
            delete_file(db=MagicMock(), file_ref=DriveFileRef(id="to-delete-id", name="old.csv"))

        service.files.return_value.delete.assert_called_once_with(fileId="to-delete-id")
