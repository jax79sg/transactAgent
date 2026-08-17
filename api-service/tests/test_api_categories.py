class TestCategoriesApi:
    def test_add_and_list_category(self, client, auth_headers):
        response = client.post("/categories", json={"name": "Groceries"}, headers=auth_headers)
        assert response.status_code == 201
        assert response.json()["name"] == "Groceries"
        assert response.json()["transactionCount"] == 0  # brand new -- can't have any yet

        response = client.get("/categories", headers=auth_headers)
        assert response.status_code == 200
        names = [c["name"] for c in response.json()]
        assert "Groceries" in names

    def test_list_categories_reports_transaction_count_per_category(self, client, auth_headers, db_session):
        from datetime import date
        from decimal import Decimal

        from transactagent_db.models import (
            BankStatement,
            Category,
            CategorySource,
            Transaction,
        )

        used_category = Category(name="Dining", active=True, is_reserved=False)
        unused_category = Category(name="Travel", active=True, is_reserved=False)
        db_session.add_all([used_category, unused_category])
        db_session.flush()
        statement = BankStatement(drive_file_id="f-usage", pdf_content_hash="e" * 64)
        db_session.add(statement)
        db_session.flush()
        db_session.add_all(
            [
                Transaction(
                    bank_statement_id=statement.id,
                    transaction_date=date(2026, 1, i),
                    description=f"Meal {i}",
                    out_flow=Decimal("10.00"),
                    currency="SGD",
                    bank_name="DBS",
                    category_id=used_category.id,
                    category_source=CategorySource.MANUAL,
                )
                for i in (1, 2)
            ]
        )
        db_session.flush()

        response = client.get("/categories", headers=auth_headers)
        assert response.status_code == 200
        by_name = {c["name"]: c["transactionCount"] for c in response.json()}

        assert by_name["Dining"] == 2
        assert by_name["Travel"] == 0

    def test_rename_category_response_reflects_its_actual_usage_count(self, client, auth_headers, db_session):
        from datetime import date
        from decimal import Decimal

        from transactagent_db.models import (
            BankStatement,
            Category,
            CategorySource,
            Transaction,
        )

        category = Category(name="Shopping", active=True, is_reserved=False)
        db_session.add(category)
        db_session.flush()
        statement = BankStatement(drive_file_id="f-rename", pdf_content_hash="f" * 64)
        db_session.add(statement)
        db_session.flush()
        db_session.add(
            Transaction(
                bank_statement_id=statement.id,
                transaction_date=date(2026, 1, 1),
                description="Amazon",
                out_flow=Decimal("50.00"),
                currency="SGD",
                bank_name="DBS",
                category_id=category.id,
                category_source=CategorySource.MANUAL,
            )
        )
        db_session.flush()

        response = client.put(f"/categories/{category.id}", json={"name": "Online Shopping"}, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["transactionCount"] == 1

    def test_add_duplicate_name_returns_400(self, client, auth_headers):
        client.post("/categories", json={"name": "Dining"}, headers=auth_headers)
        response = client.post("/categories", json={"name": "Dining"}, headers=auth_headers)
        assert response.status_code == 400
        assert response.json()["error"] == "duplicate_category_name"

    def test_remove_category_in_use_returns_409(self, client, auth_headers, db_session):
        from datetime import date
        from decimal import Decimal

        from transactagent_db.models import (
            BankStatement,
            Category,
            CategorySource,
            Transaction,
        )

        category = Category(name="Transport", active=True, is_reserved=False)
        db_session.add(category)
        db_session.flush()
        statement = BankStatement(drive_file_id="f1", pdf_content_hash="z" * 64)
        db_session.add(statement)
        db_session.flush()
        db_session.add(
            Transaction(
                bank_statement_id=statement.id,
                transaction_date=date(2026, 1, 1),
                description="Grab",
                out_flow=Decimal("10.00"),
                currency="SGD",
                bank_name="DBS",
                category_id=category.id,
                category_source=CategorySource.MANUAL,
            )
        )
        db_session.flush()

        response = client.delete(f"/categories/{category.id}", headers=auth_headers)
        assert response.status_code == 409
        assert response.json()["details"]["blockedByTransactionCount"] == 1
