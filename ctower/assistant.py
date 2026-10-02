"""Question answering over the control tower data.

Two modes:
 * default: simple rules that read the data and write a plain-English answer
 * if ANTHROPIC_API_KEY is set (and the `anthropic` package is installed), the same
   facts are sent to an LLM as context and the LLM writes the answer.
The LLM only ever sees numbers pulled from the database, which keeps answers grounded.
"""
import os
import re

PO_RE = re.compile(r"\b(4500\d{6})\b")


def _fmt_eur(x):
    return f"EUR {x:,.0f}"


def explain_order(tower, po):
    r = tower.order(po)
    if r is None:
        return f"I could not find PO {po}."
    lines = [f"PO {po} from {r.supplier_name}: status is {r.status.lower()}, value {_fmt_eur(r.ordered_value)}."]
    if r.status == "Open":
        lines.append(f"Requested date is {r.requested_date:%d %b %Y}; the supplier promised to ship on "
                     f"{r.promised_ship_date:%d %b %Y} and no ASN has arrived yet.")
    else:
        lines.append(f"Shipped {r.ship_date:%d %b} by {r.carrier} ({r["mode"]}) from {r.origin} to {r.destination}, "
                     f"{int(r.ship_delay_days)} day(s) versus the promised ship date.")
    if r.status == "Delivered":
        lines.append(f"Delivered {r.delivery_date:%d %b}, which is {int(r.delay_days)} day(s) "
                     f"{'late' if r.delay_days > 0 else 'on time or early'} against the requested date.")
    if r.status == "In transit":
        lines.append(f"The model puts the delay probability at {r.delay_prob:.0%} ({r.risk_band} risk). "
                     f"The main drivers are the ship delay of {int(r.ship_delay_days)} day(s) and "
                     f"a window of {int(r.slack_days)} day(s) between the promised ship date and the requested date "
                     f"to cover transit by {r['mode'].lower()}.")
    ex = tower.order_exceptions(po)
    if len(ex):
        lines.append("Open exceptions: " + "; ".join(f"{e.exception_type} ({e.severity})" for e in ex.itertuples()) + ".")
    return "\n".join(lines)


def _worst_suppliers(tower, n=3):
    s = tower.suppliers().head(n)
    return "Weakest suppliers by scorecard:\n" + "\n".join(
        f"- {r.supplier_name}: on-time {r.otd_pct:.0f}%, fill rate {r.fill_rate_pct:.0f}%, score {r.score}"
        for r in s.itertuples())


def _top_risk(tower, n=5):
    t = tower.in_transit().head(n)
    return "Highest-risk shipments in transit:\n" + "\n".join(
        f"- {r.po_number} ({r.supplier_name}): {r.delay_prob:.0%} delay probability, {_fmt_eur(r.ordered_value)}"
        for r in t.itertuples())


def _invoice_issues(tower):
    ex = tower.exceptions
    inv = ex[ex.exception_type.str.startswith("INVOICE")]
    top = inv.sort_values("value_eur", ascending=False).head(5)
    return (f"{len(inv)} invoice mismatches found, worth {_fmt_eur(inv.value_eur.sum())} in total. Largest:\n" +
            "\n".join(f"- {r.po_number}: {r.detail}" for r in top.itertuples()))


def _overview(tower):
    k = tower.kpis()
    return (f"{k['delivered']} orders delivered with {k['on_time_delivery_pct']}% on time. "
            f"{k['in_transit']} shipments are in transit, {k['shipments_at_risk']} of them at risk "
            f"({_fmt_eur(k['value_at_risk_eur'])}). Invoice accuracy is {k['invoice_accuracy_pct']}%.")


def rule_answer(tower, question):
    q = question.lower()
    m = PO_RE.search(question)
    if m:
        return explain_order(tower, m.group(1))
    if "supplier" in q or "vendor" in q:
        return _worst_suppliers(tower)
    if "invoice" in q or "billing" in q:
        return _invoice_issues(tower)
    if any(w in q for w in ("risk", "late", "delay", "transit")):
        return _top_risk(tower)
    return _overview(tower)


def _context(tower, question):
    m = PO_RE.search(question)
    parts = ["KPIs: " + str(tower.kpis()), _worst_suppliers(tower), _top_risk(tower), _invoice_issues(tower)]
    if m:
        parts.append(explain_order(tower, m.group(1)))
    return "\n\n".join(parts)


def answer(tower, question):
    key = os.getenv("ANTHROPIC_API_KEY")
    if key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            msg = client.messages.create(
                model=os.getenv("LLM_MODEL", "claude-sonnet-5-5"), max_tokens=500,
                system=("You are a supply chain analyst. Answer only from the data provided. "
                        "If the data does not contain the answer, say so. Be concise."),
                messages=[{"role": "user", "content": f"Data:\n{_context(tower, question)}\n\nQuestion: {question}"}])
            return msg.content[0].text
        except Exception as e:  # network, key or package problems: fall back to rules
            return rule_answer(tower, question) + f"\n\n(LLM unavailable, used rule-based answer: {type(e).__name__})"
    return rule_answer(tower, question)
