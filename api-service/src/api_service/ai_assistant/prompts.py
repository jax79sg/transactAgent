"""Prompt construction for Ask AI (US-6.1)."""

from transactagent_db.models import Transaction

_SYSTEM_PREAMBLE = """You are a financial assistant helping the user understand their own bank \
transaction history. You have been given real transactions from their account(s) below as \
ground truth — answer using ONLY this data. If the data doesn't contain enough information \
to answer confidently, say so explicitly rather than guessing.

You are not a licensed financial advisor. Frame your answer as an observation grounded in \
the data, not authoritative financial, legal, or tax advice. If the question calls for \
advice beyond what this data can show, say so and suggest the user verify with their bank \
or a qualified professional."""


def _transaction_to_csv_row(txn: Transaction) -> str:
    if txn.out_flow is not None:
        direction, amount = "out", txn.out_flow
    else:
        direction, amount = "in", txn.in_flow
    converted = txn.converted_amount_sgd if txn.converted_amount_sgd is not None else ""
    description = txn.description.replace('"', '""')
    return (
        f'{txn.transaction_date.isoformat()},"{description}",{direction},{amount},'
        f"{txn.currency},{converted},{txn.bank_name},{txn.category.name}"
    )


def build_prompt(
    question: str, transactions: list[Transaction], truncated: bool, scope_description: str
) -> str:
    csv_lines = ["date,description,direction,amount,currency,converted_sgd,bank,category"]
    csv_lines.extend(_transaction_to_csv_row(txn) for txn in transactions)
    csv_block = "\n".join(csv_lines)

    truncation_note = (
        f"\n\nNote: this is the {len(transactions)} most recent matching transactions — more "
        "exist in the selected scope but were left out to keep this within size limits. If your "
        "question likely depends on older transactions, say so."
        if truncated
        else ""
    )

    return f"""{_SYSTEM_PREAMBLE}

Scope: {scope_description} ({len(transactions)} transaction(s)).{truncation_note}

Transactions (CSV):
{csv_block}

User's question: {question}

Answer clearly and concisely, referencing specific transactions (date, description, amount) \
from the data above where relevant."""
