"""Streamlit dashboard. Run with:  streamlit run dashboard/app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plotly.express as px
import streamlit as st

from ctower import assistant, config
from ctower.service import ControlTower

st.set_page_config(page_title="Supply Chain Control Tower", layout="wide")


@st.cache_resource
def load():
    return ControlTower()


if not config.DB_PATH.exists():
    st.error("Database not found. Run `python -m ctower.pipeline` first.")
    st.stop()

tower = load()
k = tower.kpis()

st.title("EDI-Driven Supply Chain Control Tower")
st.caption("Predictive Shipment Risk & Exception Management")
st.caption(f"Simulated data as of {config.AS_OF:%d %B %Y}  |  Varun Bhadana")

tab_over, tab_risk, tab_sup, tab_exc, tab_ai, tab_model = st.tabs(
    ["Overview", "Shipment risk", "Suppliers", "Exceptions", "Ask the tower", "Model"])

with tab_over:
    c = st.columns(5)
    c[0].metric("On-time delivery", f"{k['on_time_delivery_pct']}%")
    c[1].metric("Avg lead time", f"{k['avg_lead_time_days']} d")
    c[2].metric("Fill rate", f"{k['fill_rate_pct']}%")
    c[3].metric("Invoice accuracy", f"{k['invoice_accuracy_pct']}%")
    c[4].metric("At-risk shipments", k["shipments_at_risk"], f"EUR {k['value_at_risk_eur']:,.0f}", delta_color="off")
    left, right = st.columns([2, 1])
    left.plotly_chart(px.line(tower.monthly_otd(), x="month", y="otd_pct", markers=True,
                              title="On-time delivery by month (%)"), use_container_width=True)
    status = tower.orders.status.value_counts().reset_index()
    right.plotly_chart(px.bar(status, x="status", y="count", title="Orders by status"), use_container_width=True)

with tab_risk:
    t = tower.in_transit()
    st.write(f"{len(t)} shipments in transit. Sorted by predicted delay probability.")
    show = t[["po_number", "supplier_name", "carrier", "mode", "destination", "ship_date",
              "requested_date", "ordered_value", "delay_prob", "risk_band"]]
    st.dataframe(show, use_container_width=True, hide_index=True)
    st.plotly_chart(px.histogram(t, x="delay_prob", nbins=20, color="mode",
                                 title="Distribution of delay probability"), use_container_width=True)

with tab_sup:
    s = tower.suppliers()
    st.dataframe(s, use_container_width=True, hide_index=True)
    st.plotly_chart(px.scatter(s, x="otd_pct", y="fill_rate_pct", size="orders", text="supplier_id",
                               title="On-time % vs fill rate (bubble = number of orders)"), use_container_width=True)
    st.subheader("Carriers")
    st.dataframe(tower.carriers(), use_container_width=True, hide_index=True)

with tab_exc:
    e = tower.exceptions
    f1, f2 = st.columns(2)
    sev = f1.multiselect("Severity", ["High", "Medium", "Low"], default=["High"])
    typ = f2.multiselect("Type", sorted(e.exception_type.unique()))
    e = e[e.severity.isin(sev)]
    if typ:
        e = e[e.exception_type.isin(typ)]
    st.write(f"{len(e)} exceptions, total value EUR {e.value_eur.sum():,.0f}")
    st.dataframe(e, use_container_width=True, hide_index=True)
    counts = tower.exceptions.groupby(["exception_type", "severity"]).size().reset_index(name="n")
    st.plotly_chart(px.bar(counts, x="exception_type", y="n", color="severity",
                           title="Exceptions by type"), use_container_width=True)

with tab_ai:
    st.write("Ask about a PO number (e.g. one from the risk table), suppliers, invoices or delays.")
    q = st.text_input("Question", "Which shipments are most at risk?")
    if q:
        st.text(assistant.answer(tower, q))

with tab_model:
    m = tower.model_metrics()
    st.write("Gradient boosting classifier, time-based train/test split.")
    a = st.columns(4)
    a[0].metric("ROC AUC", m.get("roc_auc"))
    a[1].metric("Precision", m.get("precision"))
    a[2].metric("Recall", m.get("recall"))
    a[3].metric("Accuracy", m.get("accuracy"))
    fi = m.get("feature_importance", {})
    st.plotly_chart(px.bar(x=list(fi.values()), y=list(fi.keys()), orientation="h",
                           title="Permutation importance (drop in AUC)").update_yaxes(autorange="reversed"),
                    use_container_width=True)
