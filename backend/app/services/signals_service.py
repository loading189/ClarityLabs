from __future__ import annotations

from dataclasses import asdict
from datetime import date
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.app.models import Account, Business, Category, HealthSignalState, RawEvent, TxnCategorization
from backend.app.norma.from_events import raw_event_to_txn
from backend.app.norma.ledger import LedgerIntegrityError, build_cash_ledger
from backend.app.norma.normalize import NormalizedTransaction
from backend.app.services import audit_service, health_signal_service


logger = logging.getLogger(__name__)


SIGNAL_CATALOG: Dict[str, Dict[str, Any]] = {
    "expense_creep_by_vendor": {
        "signal_id": "expense_creep_by_vendor",
        "domain": "expense",
        "title": "Expense creep by vendor",
        "description": "Identifies vendors with a sustained increase in outflows over a recent window.",
        "default_severity": "warning",
        "recommended_actions": [
            "Review vendor invoices for pricing changes.",
            "Confirm contract terms and check for duplicate charges.",
            "Identify opportunities to renegotiate or consolidate spend.",
        ],
        "evidence_schema": [
            "vendor_name",
            "current_total",
            "prior_total",
            "delta",
            "increase_pct",
            "window_days",
            "threshold_pct",
            "min_delta",
            "current_window.start",
            "current_window.end",
            "prior_window.start",
            "prior_window.end",
        ],
        "scoring_profile": {"weight": 1.1, "domain_weight": 1.0},
    },
    "low_cash_runway": {
        "signal_id": "low_cash_runway",
        "domain": "liquidity",
        "title": "Low cash runway",
        "description": "Detects when cash runway falls below defined thresholds based on recent burn.",
        "default_severity": "critical",
        "recommended_actions": [
            "Reforecast cash flow and adjust discretionary spend.",
            "Accelerate collections or delay noncritical outflows.",
            "Review burn assumptions and update runway targets.",
        ],
        "evidence_schema": [
            "current_cash",
            "runway_days",
            "burn_window_days",
            "total_inflow",
            "total_outflow",
            "net_burn",
            "burn_per_day",
            "burn_start",
            "burn_end",
            "thresholds.high",
            "thresholds.medium",
        ],
        "scoring_profile": {"weight": 1.6, "domain_weight": 1.3},
    },
    "unusual_outflow_spike": {
        "signal_id": "unusual_outflow_spike",
        "domain": "expense",
        "title": "Unusual outflow spike",
        "description": "Flags outflow spikes that deviate from recent spending patterns.",
        "default_severity": "warning",
        "recommended_actions": [
            "Validate the transaction details for one-off expenses.",
            "Confirm approvals for unusually large payments.",
            "Investigate potential anomalies or fraud.",
        ],
        "evidence_schema": [
            "latest_date",
            "latest_total",
            "mean_30d",
            "std_30d",
            "sigma_threshold",
            "trailing_mean_days",
            "trailing_mean",
            "mult_threshold",
            "window_days",
            "spike_sigma",
            "spike_mult",
        ],
        "scoring_profile": {"weight": 0.9, "domain_weight": 1.0},
    },
    "liquidity.runway_low": {
        "signal_id": "liquidity.runway_low",
        "domain": "liquidity",
        "title": "Low cash runway",
        "description": "Cash runway is below target based on recent burn rate.",
        "default_severity": "critical",
        "recommended_actions": [
            "Review near-term cash needs and adjust spending.",
            "Accelerate collections or extend payment terms.",
            "Update cash runway assumptions in forecasts.",
        ],
        "evidence_schema": [
            "current_cash",
            "runway_days",
            "burn_window_days",
            "total_inflow",
            "total_outflow",
            "net_burn",
            "burn_per_day",
            "burn_start",
            "burn_end",
            "thresholds.high",
            "thresholds.medium",
        ],
        "scoring_profile": {"weight": 1.8, "domain_weight": 1.4},
    },
    "liquidity.cash_trend_down": {
        "signal_id": "liquidity.cash_trend_down",
        "domain": "liquidity",
        "title": "Cash balance trending down",
        "description": "Average cash balance has declined versus the prior period.",
        "default_severity": "warning",
        "recommended_actions": [
            "Inspect recent cash outflows and adjust spending.",
            "Check for delayed collections or missing inflows.",
            "Plan for short-term liquidity buffers.",
        ],
        "evidence_schema": [
            "current_window.start",
            "current_window.end",
            "prior_window.start",
            "prior_window.end",
            "current_avg_balance",
            "prior_avg_balance",
            "delta",
            "decline_pct",
        ],
        "scoring_profile": {"weight": 1.4, "domain_weight": 1.2},
    },
    "revenue.decline_vs_baseline": {
        "signal_id": "revenue.decline_vs_baseline",
        "domain": "revenue",
        "title": "Revenue decline vs baseline",
        "description": "Recent inflows are down compared to the prior period.",
        "default_severity": "warning",
        "recommended_actions": [
            "Review top revenue drivers and customer churn.",
            "Validate pipeline or sales activity changes.",
            "Investigate seasonality impacts on inflows.",
        ],
        "evidence_schema": [
            "current_window.start",
            "current_window.end",
            "prior_window.start",
            "prior_window.end",
            "current_total",
            "prior_total",
            "delta",
            "decline_pct",
        ],
        "scoring_profile": {"weight": 1.3, "domain_weight": 1.1},
    },
    "revenue.volatility_spike": {
        "signal_id": "revenue.volatility_spike",
        "domain": "revenue",
        "title": "Revenue volatility spike",
        "description": "Revenue volatility increased materially versus the prior period.",
        "default_severity": "warning",
        "recommended_actions": [
            "Investigate large revenue swings or delayed receipts.",
            "Confirm payment terms and billing cadence.",
            "Plan for buffer if volatility persists.",
        ],
        "evidence_schema": [
            "current_window.start",
            "current_window.end",
            "prior_window.start",
            "prior_window.end",
            "current_std",
            "prior_std",
            "ratio",
        ],
        "scoring_profile": {"weight": 1.1, "domain_weight": 1.1},
    },
    "expense.spike_vs_baseline": {
        "signal_id": "expense.spike_vs_baseline",
        "domain": "expense",
        "title": "Expense spike vs baseline",
        "description": "Recent outflows spiked relative to baseline levels.",
        "default_severity": "warning",
        "recommended_actions": [
            "Review recent high-value outflows.",
            "Verify approvals for unexpected spend.",
            "Check if the spike is one-off or recurring.",
        ],
        "evidence_schema": [
            "current_window.start",
            "current_window.end",
            "prior_window.start",
            "prior_window.end",
            "current_total",
            "baseline_avg",
            "ratio",
            "delta",
        ],
        "scoring_profile": {"weight": 1.2, "domain_weight": 1.1},
    },
    "expense.new_recurring": {
        "signal_id": "expense.new_recurring",
        "domain": "expense",
        "title": "New recurring expense",
        "description": "New recurring vendor charges detected in the recent window.",
        "default_severity": "warning",
        "recommended_actions": [
            "Verify the vendor contract or subscription.",
            "Ensure the charge aligns with expected spend.",
            "Confirm correct categorization.",
        ],
        "evidence_schema": [
            "vendor_name",
            "txn_count",
            "total_amount",
            "first_seen",
            "last_seen",
            "window_days",
        ],
        "scoring_profile": {"weight": 1.0, "domain_weight": 1.0},
    },
    "timing.inflow_outflow_mismatch": {
        "signal_id": "timing.inflow_outflow_mismatch",
        "domain": "timing",
        "title": "Inflow/outflow timing mismatch",
        "description": "Outflows cluster earlier than inflows in the same window.",
        "default_severity": "warning",
        "recommended_actions": [
            "Align payment schedules with collection timing.",
            "Review operating cash buffers for timing gaps.",
        ],
        "evidence_schema": [
            "window_start",
            "window_end",
            "inflow_centroid",
            "outflow_centroid",
            "centroid_gap_days",
            "inflow_total",
            "outflow_total",
        ],
        "scoring_profile": {"weight": 1.1, "domain_weight": 1.0},
    },
    "timing.payroll_rent_cliff": {
        "signal_id": "timing.payroll_rent_cliff",
        "domain": "timing",
        "title": "Payroll/rent cash cliff",
        "description": "Payroll or rent outflows are concentrated into a single day.",
        "default_severity": "warning",
        "recommended_actions": [
            "Stagger payroll or rent payments if possible.",
            "Maintain liquidity buffers around cliff days.",
        ],
        "evidence_schema": [
            "window_start",
            "window_end",
            "cliff_date",
            "cliff_total",
            "outflow_total",
            "cliff_ratio",
        ],
        "scoring_profile": {"weight": 1.0, "domain_weight": 1.0},
    },
    "concentration.revenue_top_customer": {
        "signal_id": "concentration.revenue_top_customer",
        "domain": "concentration",
        "title": "Revenue concentration: top customer",
        "description": "Revenue is concentrated in a single customer/source.",
        "default_severity": "warning",
        "recommended_actions": [
            "Assess customer concentration risk.",
            "Diversify revenue sources where possible.",
        ],
        "evidence_schema": [
            "window_start",
            "window_end",
            "counterparty_name",
            "counterparty_total",
            "total_amount",
            "share",
        ],
        "scoring_profile": {"weight": 0.9, "domain_weight": 0.9},
    },
    "concentration.expense_top_vendor": {
        "signal_id": "concentration.expense_top_vendor",
        "domain": "concentration",
        "title": "Expense concentration: top vendor",
        "description": "Spend is concentrated in a single vendor/source.",
        "default_severity": "warning",
        "recommended_actions": [
            "Review vendor dependency risk.",
            "Explore alternative vendors or negotiate pricing.",
        ],
        "evidence_schema": [
            "window_start",
            "window_end",
            "counterparty_name",
            "counterparty_total",
            "total_amount",
            "share",
        ],
        "scoring_profile": {"weight": 0.9, "domain_weight": 0.9},
    },
    "hygiene.uncategorized_high": {
        "signal_id": "hygiene.uncategorized_high",
        "domain": "hygiene",
        "title": "High uncategorized transactions",
        "description": "A large share of transactions are uncategorized.",
        "default_severity": "info",
        "recommended_actions": [
            "Review uncategorized transactions and apply rules.",
            "Confirm category mappings for new vendors.",
        ],
        "evidence_schema": [
            "window_start",
            "window_end",
            "uncategorized_count",
            "total_count",
            "uncategorized_ratio",
        ],
        "scoring_profile": {"weight": 0.7, "domain_weight": 0.8},
    },
    "hygiene.signal_flapping": {
        "signal_id": "hygiene.signal_flapping",
        "domain": "hygiene",
        "title": "Signal flapping detected",
        "description": "A signal is repeatedly opening/resolving in a short window.",
        "default_severity": "warning",
        "recommended_actions": [
            "Review detector thresholds for stability.",
            "Investigate noisy or intermittent data sources.",
        ],
        "evidence_schema": [
            "signal_id",
            "change_count",
            "window_days",
            "window_start",
            "window_end",
        ],
        "scoring_profile": {"weight": 0.8, "domain_weight": 0.8},
    },
}

EVIDENCE_FIELDS: Dict[str, List[Dict[str, Any]]] = {
    "expense_creep_by_vendor": [
        {
            "key": "vendor_name",
            "label": "Vendor",
            "path": "vendor_name",
            "source": "ledger",
            "anchors": {"vendor_path": "vendor_name"},
        },
        {
            "key": "current_total",
            "label": "Current total",
            "path": "current_total",
            "source": "ledger",
            "unit": "USD",
            "anchors": {
                "date_start_path": "current_window.start",
                "date_end_path": "current_window.end",
                "vendor_path": "vendor_name",
            },
        },
        {
            "key": "prior_total",
            "label": "Prior total",
            "path": "prior_total",
            "source": "ledger",
            "unit": "USD",
            "anchors": {
                "date_start_path": "prior_window.start",
                "date_end_path": "prior_window.end",
                "vendor_path": "vendor_name",
            },
        },
        {
            "key": "delta",
            "label": "Delta",
            "path": "delta",
            "source": "derived",
            "unit": "USD",
            "anchors": {
                "date_start_path": "prior_window.start",
                "date_end_path": "current_window.end",
                "vendor_path": "vendor_name",
            },
        },
        {
            "key": "increase_pct",
            "label": "Increase (%)",
            "path": "increase_pct",
            "source": "derived",
            "unit": "%",
        },
        {"key": "window_days", "label": "Window (days)", "path": "window_days", "source": "state"},
        {
            "key": "threshold_pct",
            "label": "Threshold (%)",
            "path": "threshold_pct",
            "source": "state",
            "unit": "%",
        },
        {"key": "min_delta", "label": "Minimum delta", "path": "min_delta", "source": "state"},
        {
            "key": "current_window.start",
            "label": "Current window start",
            "path": "current_window.start",
            "source": "state",
            "as_of_path": "current_window.start",
        },
        {
            "key": "current_window.end",
            "label": "Current window end",
            "path": "current_window.end",
            "source": "state",
            "as_of_path": "current_window.end",
        },
        {
            "key": "prior_window.start",
            "label": "Prior window start",
            "path": "prior_window.start",
            "source": "state",
            "as_of_path": "prior_window.start",
        },
        {
            "key": "prior_window.end",
            "label": "Prior window end",
            "path": "prior_window.end",
            "source": "state",
            "as_of_path": "prior_window.end",
        },
    ],
    "low_cash_runway": [
        {
            "key": "current_cash",
            "label": "Current cash",
            "path": "current_cash",
            "source": "ledger",
            "unit": "USD",
            "anchors": {"date_end_path": "burn_end"},
        },
        {
            "key": "runway_days",
            "label": "Runway (days)",
            "path": "runway_days",
            "source": "derived",
        },
        {"key": "burn_window_days", "label": "Burn window (days)", "path": "burn_window_days", "source": "state"},
        {
            "key": "total_inflow",
            "label": "Total inflow",
            "path": "total_inflow",
            "source": "ledger",
            "unit": "USD",
            "anchors": {"date_start_path": "burn_start", "date_end_path": "burn_end"},
        },
        {
            "key": "total_outflow",
            "label": "Total outflow",
            "path": "total_outflow",
            "source": "ledger",
            "unit": "USD",
            "anchors": {"date_start_path": "burn_start", "date_end_path": "burn_end"},
        },
        {"key": "net_burn", "label": "Net burn", "path": "net_burn", "source": "derived", "unit": "USD"},
        {
            "key": "burn_per_day",
            "label": "Burn per day",
            "path": "burn_per_day",
            "source": "derived",
            "unit": "USD",
        },
        {
            "key": "burn_start",
            "label": "Burn start",
            "path": "burn_start",
            "source": "state",
            "as_of_path": "burn_start",
        },
        {
            "key": "burn_end",
            "label": "Burn end",
            "path": "burn_end",
            "source": "state",
            "as_of_path": "burn_end",
        },
        {"key": "thresholds.high", "label": "High threshold (days)", "path": "thresholds.high", "source": "state"},
        {"key": "thresholds.medium", "label": "Medium threshold (days)", "path": "thresholds.medium", "source": "state"},
    ],
    "unusual_outflow_spike": [
        {
            "key": "latest_date",
            "label": "Latest date",
            "path": "latest_date",
            "source": "ledger",
            "anchors": {"date_start_path": "latest_date", "date_end_path": "latest_date"},
        },
        {
            "key": "latest_total",
            "label": "Latest total",
            "path": "latest_total",
            "source": "ledger",
            "unit": "USD",
            "anchors": {"date_start_path": "latest_date", "date_end_path": "latest_date"},
        },
        {"key": "mean_30d", "label": "30d mean", "path": "mean_30d", "source": "derived", "unit": "USD"},
        {"key": "std_30d", "label": "30d std dev", "path": "std_30d", "source": "derived"},
        {"key": "sigma_threshold", "label": "Sigma threshold", "path": "sigma_threshold", "source": "state"},
        {"key": "trailing_mean_days", "label": "Trailing mean days", "path": "trailing_mean_days", "source": "state"},
        {"key": "trailing_mean", "label": "Trailing mean", "path": "trailing_mean", "source": "derived"},
        {"key": "mult_threshold", "label": "Multiplier threshold", "path": "mult_threshold", "source": "state"},
        {"key": "window_days", "label": "Window (days)", "path": "window_days", "source": "state"},
        {"key": "spike_sigma", "label": "Spike sigma", "path": "spike_sigma", "source": "state"},
        {"key": "spike_mult", "label": "Spike multiplier", "path": "spike_mult", "source": "state"},
    ],
    "liquidity.runway_low": [
        {
            "key": "current_cash",
            "label": "Current cash",
            "path": "current_cash",
            "source": "ledger",
            "unit": "USD",
            "anchors": {"date_end_path": "burn_end"},
        },
        {
            "key": "runway_days",
            "label": "Runway (days)",
            "path": "runway_days",
            "source": "derived",
        },
        {"key": "burn_window_days", "label": "Burn window (days)", "path": "burn_window_days", "source": "state"},
        {
            "key": "total_inflow",
            "label": "Total inflow",
            "path": "total_inflow",
            "source": "ledger",
            "unit": "USD",
            "anchors": {
                "date_start_path": "burn_start",
                "date_end_path": "burn_end",
                "txn_ids_path": "txn_ids",
            },
        },
        {
            "key": "total_outflow",
            "label": "Total outflow",
            "path": "total_outflow",
            "source": "ledger",
            "unit": "USD",
            "anchors": {
                "date_start_path": "burn_start",
                "date_end_path": "burn_end",
                "txn_ids_path": "txn_ids",
            },
        },
        {"key": "net_burn", "label": "Net burn", "path": "net_burn", "source": "derived", "unit": "USD"},
        {
            "key": "burn_per_day",
            "label": "Burn per day",
            "path": "burn_per_day",
            "source": "derived",
            "unit": "USD",
        },
        {
            "key": "burn_start",
            "label": "Burn start",
            "path": "burn_start",
            "source": "state",
            "as_of_path": "burn_start",
        },
        {
            "key": "burn_end",
            "label": "Burn end",
            "path": "burn_end",
            "source": "state",
            "as_of_path": "burn_end",
        },
        {"key": "thresholds.high", "label": "High threshold (days)", "path": "thresholds.high", "source": "state"},
        {"key": "thresholds.medium", "label": "Medium threshold (days)", "path": "thresholds.medium", "source": "state"},
    ],
    "liquidity.cash_trend_down": [
        {
            "key": "current_avg_balance",
            "label": "Current avg balance",
            "path": "current_avg_balance",
            "source": "ledger",
            "unit": "USD",
            "anchors": {
                "date_start_path": "current_window.start",
                "date_end_path": "current_window.end",
                "txn_ids_path": "txn_ids",
            },
        },
        {
            "key": "prior_avg_balance",
            "label": "Prior avg balance",
            "path": "prior_avg_balance",
            "source": "ledger",
            "unit": "USD",
            "anchors": {
                "date_start_path": "prior_window.start",
                "date_end_path": "prior_window.end",
            },
        },
        {"key": "delta", "label": "Delta", "path": "delta", "source": "derived", "unit": "USD"},
        {"key": "decline_pct", "label": "Decline (%)", "path": "decline_pct", "source": "derived", "unit": "%"},
        {
            "key": "current_window.start",
            "label": "Current window start",
            "path": "current_window.start",
            "source": "state",
            "as_of_path": "current_window.start",
        },
        {
            "key": "current_window.end",
            "label": "Current window end",
            "path": "current_window.end",
            "source": "state",
            "as_of_path": "current_window.end",
        },
        {
            "key": "prior_window.start",
            "label": "Prior window start",
            "path": "prior_window.start",
            "source": "state",
            "as_of_path": "prior_window.start",
        },
        {
            "key": "prior_window.end",
            "label": "Prior window end",
            "path": "prior_window.end",
            "source": "state",
            "as_of_path": "prior_window.end",
        },
    ],
    "revenue.decline_vs_baseline": [
        {
            "key": "current_total",
            "label": "Current inflow",
            "path": "current_total",
            "source": "ledger",
            "unit": "USD",
            "anchors": {
                "date_start_path": "current_window.start",
                "date_end_path": "current_window.end",
                "txn_ids_path": "txn_ids",
            },
        },
        {
            "key": "prior_total",
            "label": "Prior inflow",
            "path": "prior_total",
            "source": "ledger",
            "unit": "USD",
            "anchors": {
                "date_start_path": "prior_window.start",
                "date_end_path": "prior_window.end",
            },
        },
        {"key": "delta", "label": "Delta", "path": "delta", "source": "derived", "unit": "USD"},
        {"key": "decline_pct", "label": "Decline (%)", "path": "decline_pct", "source": "derived", "unit": "%"},
        {
            "key": "current_window.start",
            "label": "Current window start",
            "path": "current_window.start",
            "source": "state",
            "as_of_path": "current_window.start",
        },
        {
            "key": "current_window.end",
            "label": "Current window end",
            "path": "current_window.end",
            "source": "state",
            "as_of_path": "current_window.end",
        },
        {
            "key": "prior_window.start",
            "label": "Prior window start",
            "path": "prior_window.start",
            "source": "state",
            "as_of_path": "prior_window.start",
        },
        {
            "key": "prior_window.end",
            "label": "Prior window end",
            "path": "prior_window.end",
            "source": "state",
            "as_of_path": "prior_window.end",
        },
    ],
    "revenue.volatility_spike": [
        {
            "key": "current_std",
            "label": "Current std dev",
            "path": "current_std",
            "source": "derived",
            "unit": "USD",
            "anchors": {
                "date_start_path": "current_window.start",
                "date_end_path": "current_window.end",
                "txn_ids_path": "txn_ids",
            },
        },
        {
            "key": "prior_std",
            "label": "Prior std dev",
            "path": "prior_std",
            "source": "derived",
            "unit": "USD",
            "anchors": {
                "date_start_path": "prior_window.start",
                "date_end_path": "prior_window.end",
            },
        },
        {"key": "ratio", "label": "Volatility ratio", "path": "ratio", "source": "derived"},
        {
            "key": "current_window.start",
            "label": "Current window start",
            "path": "current_window.start",
            "source": "state",
            "as_of_path": "current_window.start",
        },
        {
            "key": "current_window.end",
            "label": "Current window end",
            "path": "current_window.end",
            "source": "state",
            "as_of_path": "current_window.end",
        },
        {
            "key": "prior_window.start",
            "label": "Prior window start",
            "path": "prior_window.start",
            "source": "state",
            "as_of_path": "prior_window.start",
        },
        {
            "key": "prior_window.end",
            "label": "Prior window end",
            "path": "prior_window.end",
            "source": "state",
            "as_of_path": "prior_window.end",
        },
    ],
    "expense.spike_vs_baseline": [
        {
            "key": "current_total",
            "label": "Current outflow",
            "path": "current_total",
            "source": "ledger",
            "unit": "USD",
            "anchors": {
                "date_start_path": "current_window.start",
                "date_end_path": "current_window.end",
                "txn_ids_path": "txn_ids",
            },
        },
        {
            "key": "baseline_avg",
            "label": "Baseline average",
            "path": "baseline_avg",
            "source": "derived",
            "unit": "USD",
        },
        {"key": "ratio", "label": "Spike ratio", "path": "ratio", "source": "derived"},
        {"key": "delta", "label": "Delta", "path": "delta", "source": "derived", "unit": "USD"},
        {
            "key": "current_window.start",
            "label": "Current window start",
            "path": "current_window.start",
            "source": "state",
            "as_of_path": "current_window.start",
        },
        {
            "key": "current_window.end",
            "label": "Current window end",
            "path": "current_window.end",
            "source": "state",
            "as_of_path": "current_window.end",
        },
        {
            "key": "prior_window.start",
            "label": "Prior window start",
            "path": "prior_window.start",
            "source": "state",
            "as_of_path": "prior_window.start",
        },
        {
            "key": "prior_window.end",
            "label": "Prior window end",
            "path": "prior_window.end",
            "source": "state",
            "as_of_path": "prior_window.end",
        },
    ],
    "expense.new_recurring": [
        {
            "key": "vendor_name",
            "label": "Vendor",
            "path": "vendor_name",
            "source": "ledger",
            "anchors": {"txn_ids_path": "txn_ids", "vendor_path": "vendor_name"},
        },
        {"key": "txn_count", "label": "Transactions", "path": "txn_count", "source": "state"},
        {"key": "total_amount", "label": "Total amount", "path": "total_amount", "source": "ledger", "unit": "USD"},
        {
            "key": "first_seen",
            "label": "First seen",
            "path": "first_seen",
            "source": "state",
            "as_of_path": "first_seen",
        },
        {
            "key": "last_seen",
            "label": "Last seen",
            "path": "last_seen",
            "source": "state",
            "as_of_path": "last_seen",
        },
        {"key": "window_days", "label": "Window (days)", "path": "window_days", "source": "state"},
    ],
    "timing.inflow_outflow_mismatch": [
        {
            "key": "centroid_gap_days",
            "label": "Gap (days)",
            "path": "centroid_gap_days",
            "source": "derived",
        },
        {
            "key": "inflow_total",
            "label": "Inflow total",
            "path": "inflow_total",
            "source": "ledger",
            "unit": "USD",
            "anchors": {"date_start_path": "window_start", "date_end_path": "window_end"},
        },
        {
            "key": "outflow_total",
            "label": "Outflow total",
            "path": "outflow_total",
            "source": "ledger",
            "unit": "USD",
            "anchors": {
                "date_start_path": "window_start",
                "date_end_path": "window_end",
                "txn_ids_path": "txn_ids",
            },
        },
        {
            "key": "window_start",
            "label": "Window start",
            "path": "window_start",
            "source": "state",
            "as_of_path": "window_start",
        },
        {
            "key": "window_end",
            "label": "Window end",
            "path": "window_end",
            "source": "state",
            "as_of_path": "window_end",
        },
    ],
    "timing.payroll_rent_cliff": [
        {
            "key": "cliff_total",
            "label": "Cliff total",
            "path": "cliff_total",
            "source": "ledger",
            "unit": "USD",
            "anchors": {"date_start_path": "cliff_date", "date_end_path": "cliff_date", "txn_ids_path": "txn_ids"},
        },
        {
            "key": "cliff_ratio",
            "label": "Cliff ratio",
            "path": "cliff_ratio",
            "source": "derived",
        },
        {
            "key": "outflow_total",
            "label": "Outflow total",
            "path": "outflow_total",
            "source": "ledger",
            "unit": "USD",
            "anchors": {"date_start_path": "window_start", "date_end_path": "window_end"},
        },
        {
            "key": "cliff_date",
            "label": "Cliff date",
            "path": "cliff_date",
            "source": "state",
            "as_of_path": "cliff_date",
        },
        {
            "key": "window_start",
            "label": "Window start",
            "path": "window_start",
            "source": "state",
            "as_of_path": "window_start",
        },
        {
            "key": "window_end",
            "label": "Window end",
            "path": "window_end",
            "source": "state",
            "as_of_path": "window_end",
        },
    ],
    "concentration.revenue_top_customer": [
        {
            "key": "counterparty_name",
            "label": "Top customer",
            "path": "counterparty_name",
            "source": "ledger",
            "anchors": {"txn_ids_path": "txn_ids", "vendor_path": "counterparty_name"},
        },
        {
            "key": "counterparty_total",
            "label": "Top customer total",
            "path": "counterparty_total",
            "source": "ledger",
            "unit": "USD",
        },
        {"key": "total_amount", "label": "Total inflow", "path": "total_amount", "source": "ledger", "unit": "USD"},
        {"key": "share", "label": "Share", "path": "share", "source": "derived"},
        {
            "key": "window_start",
            "label": "Window start",
            "path": "window_start",
            "source": "state",
            "as_of_path": "window_start",
        },
        {
            "key": "window_end",
            "label": "Window end",
            "path": "window_end",
            "source": "state",
            "as_of_path": "window_end",
        },
    ],
    "concentration.expense_top_vendor": [
        {
            "key": "counterparty_name",
            "label": "Top vendor",
            "path": "counterparty_name",
            "source": "ledger",
            "anchors": {"txn_ids_path": "txn_ids", "vendor_path": "counterparty_name"},
        },
        {
            "key": "counterparty_total",
            "label": "Top vendor total",
            "path": "counterparty_total",
            "source": "ledger",
            "unit": "USD",
        },
        {"key": "total_amount", "label": "Total outflow", "path": "total_amount", "source": "ledger", "unit": "USD"},
        {"key": "share", "label": "Share", "path": "share", "source": "derived"},
        {
            "key": "window_start",
            "label": "Window start",
            "path": "window_start",
            "source": "state",
            "as_of_path": "window_start",
        },
        {
            "key": "window_end",
            "label": "Window end",
            "path": "window_end",
            "source": "state",
            "as_of_path": "window_end",
        },
    ],
    "hygiene.uncategorized_high": [
        {
            "key": "uncategorized_count",
            "label": "Uncategorized count",
            "path": "uncategorized_count",
            "source": "ledger",
            "anchors": {"txn_ids_path": "txn_ids"},
        },
        {
            "key": "total_count",
            "label": "Total count",
            "path": "total_count",
            "source": "derived",
        },
        {
            "key": "uncategorized_ratio",
            "label": "Uncategorized ratio",
            "path": "uncategorized_ratio",
            "source": "derived",
        },
        {
            "key": "window_start",
            "label": "Window start",
            "path": "window_start",
            "source": "state",
            "as_of_path": "window_start",
        },
        {
            "key": "window_end",
            "label": "Window end",
            "path": "window_end",
            "source": "state",
            "as_of_path": "window_end",
        },
    ],
    "hygiene.signal_flapping": [
        {"key": "signal_id", "label": "Signal ID", "path": "signal_id", "source": "state"},
        {"key": "change_count", "label": "Change count", "path": "change_count", "source": "state"},
        {"key": "window_days", "label": "Window (days)", "path": "window_days", "source": "state"},
        {"key": "window_start", "label": "Window start", "path": "window_start", "source": "state"},
        {"key": "window_end", "label": "Window end", "path": "window_end", "source": "state"},
    ],
}

AUDIT_EVENT_TYPES = {
    "signal_detected",
    "signal_updated",
    "signal_resolved",
    "signal_status_changed",
}


def _is_dev_env() -> bool:
    return (
        os.getenv("ENV", "").lower() in {"dev", "development", "local"}
        or os.getenv("APP_ENV", "").lower() in {"dev", "development", "local"}
        or os.getenv("NODE_ENV", "").lower() in {"dev", "development"}
    )


def v1_signals_enabled() -> bool:
    return os.getenv("ENABLE_V1_SIGNALS", "").strip().lower() in {"1", "true", "yes", "on"}


def _require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")
    return biz


def _date_range_filter(occurred_at: date, start: date, end: date) -> bool:
    return start <= occurred_at <= end


def _fetch_posted_transactions(
    db: Session,
    business_id: str,
    start_date: date,
    end_date: date,
) -> List[NormalizedTransaction]:
    stmt = (
        select(TxnCategorization, RawEvent, Category, Account)
        .join(
            RawEvent,
            and_(
                RawEvent.business_id == TxnCategorization.business_id,
                RawEvent.source_event_id == TxnCategorization.source_event_id,
            ),
        )
        .join(Category, Category.id == TxnCategorization.category_id)
        .join(Account, Account.id == Category.account_id)
        .where(TxnCategorization.business_id == business_id)
        .order_by(RawEvent.occurred_at.asc(), RawEvent.source_event_id.asc())
    )

    rows = db.execute(stmt).all()
    txns: List[NormalizedTransaction] = []
    for _, ev, cat, acct in rows:
        if not _date_range_filter(ev.occurred_at.date(), start_date, end_date):
            continue
        txn = raw_event_to_txn(ev.payload, ev.occurred_at, ev.source_event_id)
        txns.append(
            NormalizedTransaction(
                id=txn.id,
                source_event_id=txn.source_event_id,
                occurred_at=txn.occurred_at,
                date=txn.date,
                description=txn.description,
                amount=txn.amount,
                direction=txn.direction,
                account=acct.name,
                category=(cat.name or cat.system_key or "uncategorized"),
                counterparty_hint=txn.counterparty_hint,
            )
        )

    return txns


def fetch_signals(
    db: Session,
    business_id: str,
    start_date: date,
    end_date: date,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not v1_signals_enabled():
        raise HTTPException(status_code=404, detail="v1 signals disabled")
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date range: {start_date} → {end_date}",
        )

    _require_business(db, business_id)

    txns = _fetch_posted_transactions(db, business_id, start_date, end_date)
    if not txns:
        return [], {
            "reason": "not_enough_data",
            "detail": "No posted transactions in the selected date range.",
        }

    try:
        ledger = build_cash_ledger(txns, opening_balance=0.0)
        from backend.app.signals.core import generate_core_signals

        signals = generate_core_signals(txns, ledger)
    except LedgerIntegrityError as exc:
        if _is_dev_env():
            logger.warning(
                "[signals] ledger integrity failed business=%s error=%s",
                business_id,
                str(exc),
            )
        return [], {
            "reason": "integrity_error",
            "detail": str(exc),
        }

    return [asdict(signal) for signal in signals], {"count": len(signals)}


def list_signal_states(db: Session, business_id: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    _require_business(db, business_id)

    rows = (
        db.execute(
            select(HealthSignalState)
            .where(HealthSignalState.business_id == business_id)
            .order_by(HealthSignalState.updated_at.desc())
        )
        .scalars()
        .all()
    )

    signals = []
    for row in rows:
        domain = None
        if row.signal_type:
            domain = SIGNAL_CATALOG.get(row.signal_type, {}).get("domain")
        signals.append(
            {
                "id": row.signal_id,
                "type": row.signal_type,
                "domain": domain,
                "severity": row.severity,
                "status": row.status,
                "title": row.title,
                "summary": row.summary,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
        )
    return signals, {"count": len(signals)}


def get_signal_state_detail(db: Session, business_id: str, signal_id: str) -> Dict[str, Any]:
    _require_business(db, business_id)
    state = db.get(HealthSignalState, (business_id, signal_id))
    if not state:
        raise HTTPException(status_code=404, detail="signal not found")
    domain = None
    if state.signal_type:
        domain = SIGNAL_CATALOG.get(state.signal_type, {}).get("domain")
    return {
        "id": state.signal_id,
        "type": state.signal_type,
        "domain": domain,
        "severity": state.severity,
        "status": state.status,
        "title": state.title,
        "summary": state.summary,
        "payload_json": state.payload_json,
        "fingerprint": state.fingerprint,
        "detected_at": state.detected_at.isoformat() if state.detected_at else None,
        "last_seen_at": state.last_seen_at.isoformat() if state.last_seen_at else None,
        "resolved_at": state.resolved_at.isoformat() if state.resolved_at else None,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def available_signal_types() -> List[Dict[str, Any]]:
    return [
        {
            "type": "cash_runway_trend",
            "window_days": 30,
            "required_inputs": ["transactions", "ledger", "outflow", "cash_balance"],
        },
        {
            "type": "expense_creep",
            "window_days": 30,
            "required_inputs": ["transactions", "outflow", "category"],
        },
        {
            "type": "revenue_volatility",
            "window_days": 60,
            "required_inputs": ["transactions", "weekly_inflows"],
        },
        {
            "type": "expense_creep_by_vendor",
            "window_days": 14,
            "required_inputs": ["transactions", "outflow", "vendor"],
        },
        {
            "type": "low_cash_runway",
            "window_days": 30,
            "required_inputs": ["transactions", "cash_series", "burn_rate"],
        },
        {
            "type": "unusual_outflow_spike",
            "window_days": 30,
            "required_inputs": ["transactions", "daily_outflow"],
        },
    ]


def update_signal_status(
    db: Session,
    business_id: str,
    signal_id: str,
    status: str,
    reason: Optional[str] = None,
    actor: Optional[str] = None,
) -> Dict[str, Any]:
    return health_signal_service.update_signal_status(
        db,
        business_id,
        signal_id,
        status=status,
        reason=reason,
        actor=actor,
    )


def _read_payload_value(payload: Dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        if part not in current:
            return None
        current = current[part]
    return current


def _build_anchors(payload: Dict[str, Any], field: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    anchor_cfg = field.get("anchors")
    if not isinstance(anchor_cfg, dict):
        return None

    anchors: Dict[str, Any] = {}
    if "txn_ids_path" in anchor_cfg:
        txn_ids = _read_payload_value(payload, anchor_cfg["txn_ids_path"])
        if isinstance(txn_ids, list):
            anchors["txn_ids"] = [str(txn_id) for txn_id in txn_ids]
    for key, target in (
        ("date_start", "date_start_path"),
        ("date_end", "date_end_path"),
        ("account_id", "account_id_path"),
        ("vendor", "vendor_path"),
        ("category", "category_path"),
    ):
        path = anchor_cfg.get(target)
        if not path:
            continue
        value = _read_payload_value(payload, path)
        if value is not None:
            anchors[key] = value

    return anchors or None


def _build_evidence(signal_type: Optional[str], payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not signal_type or not isinstance(payload, dict):
        return []
    fields = EVIDENCE_FIELDS.get(signal_type, [])
    evidence: List[Dict[str, Any]] = []
    for field in fields:
        value = _read_payload_value(payload, field["path"])
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            continue
        item: Dict[str, Any] = {
            "key": field["key"],
            "label": field["label"],
            "value": value,
            "source": field["source"],
        }
        if field.get("unit") is not None:
            item["unit"] = field["unit"]
        as_of_path = field.get("as_of_path")
        if as_of_path:
            item["as_of"] = _read_payload_value(payload, as_of_path)
        anchors = _build_anchors(payload, field)
        if anchors:
            item["anchors"] = anchors
        evidence.append(item)
    return sorted(evidence, key=lambda item: (item["key"], item["label"]))


def _detector_meta(signal_type: Optional[str], state: HealthSignalState) -> Dict[str, Any]:
    if signal_type and signal_type in SIGNAL_CATALOG:
        catalog = SIGNAL_CATALOG[signal_type]
        return {
            "type": catalog["signal_id"],
            "title": catalog["title"],
            "description": catalog["description"],
            "domain": catalog["domain"],
            "default_severity": catalog["default_severity"],
            "recommended_actions": catalog["recommended_actions"],
            "evidence_schema": catalog["evidence_schema"],
            "scoring_profile": catalog["scoring_profile"],
        }
    return {
        "type": signal_type or "unknown",
        "title": state.title or "Signal",
        "description": state.summary or "",
        "recommended_actions": [],
        "domain": "unknown",
        "default_severity": None,
        "evidence_schema": [],
        "scoring_profile": {},
    }


def _audit_references_signal(entry: Dict[str, Any], signal_id: str) -> bool:
    for key in ("before_state", "after_state"):
        state = entry.get(key)
        if isinstance(state, dict) and state.get("signal_id") == signal_id:
            return True
    return False


def _list_related_audits(
    db: Session,
    business_id: str,
    signal_id: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    payload = audit_service.list_audit_events(db, business_id, limit=50)
    items = payload.get("items", [])
    def _audit_sort_key(entry: Dict[str, Any]) -> Tuple[int, str]:
        created_at = entry.get("created_at")
        timestamp = int(created_at.timestamp()) if created_at else 0
        entry_id = str(entry.get("id") or "")
        return (-timestamp, entry_id)

    items = sorted(items, key=_audit_sort_key)
    related: List[Dict[str, Any]] = []
    for entry in items:
        if entry.get("event_type") not in AUDIT_EVENT_TYPES:
            continue
        if not _audit_references_signal(entry, signal_id):
            continue
        after_state = entry.get("after_state") or {}
        related.append(
            {
                "id": entry.get("id"),
                "event_type": entry.get("event_type"),
                "actor": entry.get("actor"),
                "reason": entry.get("reason"),
                "status": after_state.get("status"),
                "created_at": entry.get("created_at").isoformat()
                if entry.get("created_at")
                else None,
            }
        )
        if len(related) >= limit:
            break
    return related


def get_signal_explain(db: Session, business_id: str, signal_id: str) -> Dict[str, Any]:
    _require_business(db, business_id)
    state = db.get(HealthSignalState, (business_id, signal_id))
    if not state:
        raise HTTPException(status_code=404, detail="signal not found")

    evidence = _build_evidence(state.signal_type, state.payload_json)
    detector = _detector_meta(state.signal_type, state)
    related_audits = _list_related_audits(db, business_id, signal_id)

    return {
        "business_id": business_id,
        "signal_id": signal_id,
        "state": {
            "status": state.status,
            "severity": state.severity,
            "created_at": state.detected_at.isoformat() if state.detected_at else None,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
            "last_seen_at": state.last_seen_at.isoformat() if state.last_seen_at else None,
            "resolved_at": state.resolved_at.isoformat() if state.resolved_at else None,
            "metadata": state.payload_json,
        },
        "detector": detector,
        "evidence": evidence,
        "related_audits": related_audits,
        "links": [
            "/signals",
            f"/app/{business_id}/signals",
        ],
    }
