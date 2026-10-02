"""Shipment delay model.

Target: was the PO delivered after its requested date (is_late)?
Features are only things we know once the ASN (856) has arrived, so the model
can be used on shipments that are still on the way.
"""
import json

import joblib
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import precision_score, recall_score, roc_auc_score, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from . import config

NUM = ["slack_days", "ship_delay_days", "qty_ordered", "ordered_value",
       "ack_short_pct", "ship_short_pct", "ack_changed", "ship_month", "n_lines"]
CAT = ["supplier_id", "carrier", "mode", "destination"]


def _pipeline():
    pre = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), CAT),
                             ("num", "passthrough", NUM)])
    clf = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05,
                                     subsample=0.8, random_state=config.SEED)
    return Pipeline([("pre", pre), ("clf", clf)])


def train(orders):
    d = orders[orders.status == "Delivered"].sort_values("ship_date").reset_index(drop=True)
    cut = int(len(d) * 0.8)  # time-based split: train on the past, test on the most recent shipments
    tr, te = d.iloc[:cut], d.iloc[cut:]
    X = NUM + CAT

    pipe = _pipeline().fit(tr[X], tr.is_late)
    prob = pipe.predict_proba(te[X])[:, 1]
    pred = (prob >= 0.5).astype(int)
    imp = permutation_importance(pipe, te[X], te.is_late, scoring="roc_auc",
                                 n_repeats=5, random_state=config.SEED)
    metrics = {
        "train_rows": int(len(tr)), "test_rows": int(len(te)),
        "late_rate_train": round(float(tr.is_late.mean()), 3),
        "late_rate_test": round(float(te.is_late.mean()), 3),
        "roc_auc": round(float(roc_auc_score(te.is_late, prob)), 3),
        "precision": round(float(precision_score(te.is_late, pred)), 3),
        "recall": round(float(recall_score(te.is_late, pred)), 3),
        "f1": round(float(f1_score(te.is_late, pred)), 3),
        "baseline_accuracy_always_on_time": round(float(1 - te.is_late.mean()), 3),
        "accuracy": round(float((pred == te.is_late).mean()), 3),
        "feature_importance": {k: round(float(v), 4) for k, v in
                               sorted(zip(X, imp.importances_mean), key=lambda t: -t[1])},
    }
    # final model uses all delivered orders
    final = _pipeline().fit(d[X], d.is_late)
    config.MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump(final, config.MODEL_PATH)
    config.METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    return final, metrics


def score(orders, pipe):
    """Adds delay_prob / risk_band for shipments that are still in transit."""
    o = orders.copy()
    o["delay_prob"] = np.nan
    m = o.status == "In transit"
    if m.any():
        o.loc[m, "delay_prob"] = pipe.predict_proba(o.loc[m, NUM + CAT])[:, 1]
    o["risk_band"] = None
    o.loc[m, "risk_band"] = np.select(
        [o.loc[m, "delay_prob"] >= config.RISK_HIGH, o.loc[m, "delay_prob"] >= config.RISK_MEDIUM],
        ["High", "Medium"], default="Low")
    return o
