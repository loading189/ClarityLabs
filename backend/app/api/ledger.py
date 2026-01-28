from backend.app.api.routes.ledger import *  # noqa: F401,F403
from backend.app.services import ledger_service

signed_amount = ledger_service.signed_amount
is_inflow = ledger_service.is_inflow


def _build_cash_series(txns, starting_cash):
    return [CashPointOut(**item) for item in ledger_service._build_cash_series(txns, starting_cash)]
