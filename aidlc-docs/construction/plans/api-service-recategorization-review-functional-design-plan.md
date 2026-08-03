# Functional Design Plan — API Service Unit — Recategorization Review Panel

**Unit**: API Service (Unit 2). **Scope**: new Recategorization Review Component — list/pending-count/approve/reject/bulk endpoints.

## No blocking questions

Read `ingestion/{router,schemas,service,repository}.py` directly before designing — it's the closest existing analog (list + paginated history + drill-down pattern) and `transactions/repository.py`'s `joinedload` convention for DTO-ready relationship loading. Every decision below follows directly from these existing conventions plus the already-approved Application Design, not from a fresh product-owner tradeoff.

## Execution Checklist

- [x] Add AR-11 (proposal must exist), AR-12 (must be pending to resolve, BR-16 surfaced at API layer, per-item not whole-batch failure), AR-13 (approve writes through with `category_source='similarity'`, reject never touches the transaction) to `business-rules.md`
- [x] Add `ProposalDTO`, `ProposalPage`, `PendingCountResponse`, `BulkProposalRequest`, `BulkApproveResponse`, `BulkRejectResponse` to `domain-entities.md`
- [x] Add the Recategorization Review Component's logic (list/count/approve/reject/bulk) to `business-logic-model.md`
