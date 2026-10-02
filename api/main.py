"""REST API. Run with:  uvicorn api.main:app --reload   (docs at /docs)"""
from fastapi import FastAPI, HTTPException, Query

from ctower import assistant
from ctower.service import ControlTower

app = FastAPI(title="EDI-Driven Supply Chain Control Tower", version="1.0")
tower = ControlTower()


def _clean(df):
    return df.astype(object).where(df.notna(), None).to_dict(orient="records")


@app.get("/kpis")
def kpis():
    return tower.kpis()


@app.get("/suppliers")
def suppliers():
    return _clean(tower.suppliers())


@app.get("/shipments/at-risk")
def at_risk(min_prob: float = Query(0.4, ge=0, le=1)):
    t = tower.in_transit()
    t = t[t.delay_prob >= min_prob][["po_number", "supplier_name", "carrier", "mode", "destination",
                                       "ordered_value", "delay_prob", "risk_band"]]
    return _clean(t)


@app.get("/orders/{po_number}")
def order(po_number: str):
    r = tower.order(po_number)
    if r is None:
        raise HTTPException(404, f"PO {po_number} not found")
    return {"order": {k: (None if v != v else str(v)) for k, v in r.to_dict().items()},
            "exceptions": _clean(tower.order_exceptions(po_number))}


@app.get("/exceptions")
def exceptions(severity: str | None = None, type: str | None = None, limit: int = 50):
    e = tower.exceptions
    if severity:
        e = e[e.severity.str.lower() == severity.lower()]
    if type:
        e = e[e.exception_type == type.upper()]
    return _clean(e.head(limit))


@app.get("/assistant")
def ask(question: str):
    return {"question": question, "answer": assistant.answer(tower, question)}
