# Industrial Data Platform — Cloud Data Architecture for a 100-Machine CNC Fleet

> Work in progress. Full README (problem statement, scenario, datasets, run instructions, findings, architecture) is written in the final stage.

Repository layout:

```
data/       reference tables, processed Parquet snapshot, small real samples, provenance notes
python/     numbered pipeline scripts, edge/ (MQTT + features), ml/, utils/
sql/        PostgreSQL schema, load, required and advanced queries, results/
dashboard/  Streamlit multi-page app
diagrams/   architecture, data-flow, security-zone and ER diagrams
docs/       sources, cost model, viva Q&A, screenshots, figures
```
