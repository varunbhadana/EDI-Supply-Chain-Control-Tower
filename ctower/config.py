from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "control_tower.db"
MODEL_PATH = ROOT / "models" / "delay_model.joblib"
METRICS_PATH = ROOT / "docs" / "model_metrics.json"

# The simulation "today". Everything after this date has not happened yet,
# so those orders are still open or in transit.
AS_OF = date(2026, 9, 15)
SEED = 42
N_ORDERS = 900

# thresholds used by the exception engine
RISK_MEDIUM = 0.40
RISK_HIGH = 0.70
SHORT_SHIP_TOL = 0.05      # >5% below ordered qty
INVOICE_PRICE_TOL = 0.01   # >1% off the expected amount
