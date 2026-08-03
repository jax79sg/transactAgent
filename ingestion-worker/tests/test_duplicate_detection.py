from ingestion_worker.duplicate_detection import service


class TestComputeFileHash:
    def test_same_bytes_produce_same_hash(self):
        assert service.compute_file_hash(b"hello world") == service.compute_file_hash(b"hello world")

    def test_different_bytes_produce_different_hash(self):
        assert service.compute_file_hash(b"hello") != service.compute_file_hash(b"world")

    def test_hash_is_sha256_hex_digest(self):
        result = service.compute_file_hash(b"test")
        assert len(result) == 64
        int(result, 16)  # raises if not valid hex


class TestFindAndRecordProcessed:
    def test_new_hash_is_not_found(self, db_session):
        assert service.find_existing_statement(db_session, "a" * 64) is None

    def test_recorded_statement_is_then_found(self, db_session):
        service.record_processed(db_session, drive_file_id="f1", pdf_content_hash="b" * 64, bank_name="DBS")
        found = service.find_existing_statement(db_session, "b" * 64)
        assert found is not None
        assert found.bank_name == "DBS"
