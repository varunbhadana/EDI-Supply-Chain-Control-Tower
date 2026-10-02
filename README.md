# EDI-Driven Supply Chain Control Tower with Predictive Shipment Risk & Exception Management

A simulated enterprise supply chain that I built to understand how EDI messages, a data layer, a small ML model and an AI assistant fit together to give end-to-end visibility, from purchase order to invoice.

**Author:** Varun Bhadana
Political Science (Hons.), University of Delhi, applying for a Master's in Supply Chain and Global Logistics in Germany.

## Why I built this

My degree is in political science, but the topics I kept coming back to were trade policy, sanctions, port disruptions and how geopolitical events end up as late containers and empty shelves. I wanted to see that story from the operational side. Instead of only reading about supply chain risk, I wanted to build the data flow that a company uses to detect it. This project is my first step in moving from policy analysis to supply chain analytics.

## What it does

The buyer is a fictional German manufacturer ordering parts from 12 suppliers in Europe and Asia. The pipeline:

1. **Generates EDI X12 files** for 900 purchase orders: 850 (purchase order), 855 (acknowledgement), 856 (advance ship notice), 214 (shipment status) and 810 (invoice).
2. **Parses the EDI** into tables. Sets with a wrong `SE` segment count are rejected and logged rather than crashing the run.
3. **Loads a relational database** (SQLite by default, schema is plain SQL and also works on PostgreSQL).
4. **Builds one row per PO** that links order, acknowledgement, shipment, delivery event and invoice.
5. **Calculates KPIs and scorecards** for suppliers and carriers.
6. **Predicts delay probability** for shipments still in transit (gradient boosting).
7. **Raises exceptions** with a severity and a readable explanation.
8. **Serves everything** through a REST API (FastAPI), a dashboard (Streamlit/Plotly) and a question-answering assistant.

```
 850 / 855 / 856 / 214 / 810 (X12 files)
              |
        edi_parser.py   -- validation, rejects bad sets
              |
     SQL database (schema.sql)
              |
        analytics.py    -- one row per PO, KPIs, scorecards
         /          \
   model.py      exceptions.py
  (delay risk)    (rules + severity)
         \          /
          service.py
        /      |       \
   FastAPI  Streamlit  assistant.py (rules, or LLM if API key is set)
```

## Results on the simulated data (as of 15 Sep 2026)

| Metric | Value |
|---|---|
| Orders | 900 (783 delivered, 60 in transit, 57 not yet shipped) |
| On-time delivery | 61.8% |
| Fill rate | 97.6% |
| Invoice accuracy | 95.4% (34 mismatches) |
| Shipments in transit at high/medium risk | 32 (about EUR 848k of order value) |
| Exceptions raised | 545 |
| Weakest suppliers | Hanoi Cable Systems, Shenzhen Electro Parts, Pune Forgings |

### About the model, honestly

Test ROC AUC is 0.985 (precision 0.91, recall 0.90) on the most recent 20% of delivered orders. **This number is flattering and should not be read as real-world performance.** The data is simulated, and lateness is mostly determined by two things I built into the generator: how late the supplier shipped versus its promise, and how much slack was left to cover transit. The model correctly picks those up (see the permutation importance in `docs/model_metrics.json`), which shows the pipeline works, but a real company's data is far noisier. With real ASN and carrier data I would expect a much lower score and I would add weather, port congestion and customs features.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m ctower.pipeline          # generate EDI, parse, load DB, train model, find exceptions
python -m unittest discover -s tests -t .

streamlit run dashboard/app.py     # dashboard
uvicorn api.main:app --reload      # API, interactive docs at http://127.0.0.1:8000/docs
```

Optional LLM assistant: set `ANTHROPIC_API_KEY` (and optionally `LLM_MODEL`) before starting the dashboard or API. The assistant then writes answers from the same database facts. Without a key it falls back to rule-based answers, so everything runs offline.

Example API calls:

```
GET /kpis
GET /shipments/at-risk?min_prob=0.7
GET /exceptions?severity=high&type=INVOICE_PRICE_MISMATCH
GET /orders/4500000057
GET /assistant?question=Which suppliers are the weakest?
```

## Project layout

```
ctower/
  generate_edi.py   simulated X12 files
  edi_parser.py     parser and validation
  database.py       builds the database from sql/schema.sql
  analytics.py      PO-level table, KPIs, scorecards
  model.py          delay-risk model
  exceptions.py     exception rules
  assistant.py      Q&A (rules or LLM)
  pipeline.py       runs everything end to end
api/main.py         FastAPI app
dashboard/app.py    Streamlit app
sql/                schema and example analytical queries
docs/sample_edi/    a few readable example EDI documents
tests/              unit and end-to-end tests
```

## EDI segments used

| Set | Meaning | Key segments |
|---|---|---|
| 850 | Purchase order | BEG, N1, DTM, PO1 |
| 855 | PO acknowledgement | BAK, PO1, ACK |
| 856 | Advance ship notice | BSN, TD5, N1, DTM, PRF, SN1 |
| 214 | Shipment status | B10, L11, LX, AT7, MS1 |
| 810 | Invoice | BIG, IT1, TDS |

## Limitations

- All data is simulated. Suppliers, carriers and company are fictional.
- The parser covers only the segments listed above. It has no 997 functional acknowledgements, no loop validation and no partner-specific mappings.
- "Real-time" is simulated: the pipeline is a batch run with a fixed as-of date.
- Delivery date comes from the 214 `D1` event; a missing event means the order is treated as undelivered.
- The supplier score weights (50% on-time, 30% fill rate, 20% invoice accuracy) are my own choice and are easy to change in `analytics.py`.

## Ideas for next steps

- Replace SQLite with PostgreSQL through SQLAlchemy and run the ingestion on a schedule.
- Add 997 acknowledgements and a rejected-documents report.
- Add external signals (port congestion, weather, public holidays) as model features.
- Extend the cost view with expediting costs and inventory impact of late shipments.

## License

MIT, see `LICENSE`.
