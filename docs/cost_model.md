# Indicative INR cost model

Generated numbers: `python python/part_c_decision_matrix.py`. Outputs are `docs/results/part_c_cost_model.csv`, `part_c_cost_tables.md` and `part_c_summary.json`, plus the "Cost model (INR)" sheet in `docs/decision_matrix.xlsx`.

> **Indicative only.**
> - Prices are public USD list prices accessed 2026-10-21, for the India regions where the price page shows them. See [`sources.md`](sources.md) and `data/reference/cloud_prices.json`.
> - They exclude networking and egress, support plans, reservations or savings plans, GST, edge hardware, controller OPC UA licences and labour.

## Assumptions

| Item | Value | Basis |
|---|---|---|
| Exchange rate | **1 USD = ₹94.7145** | RBI/FBIL reference rate, 21 Oct 2026, 1:00 pm IST [S78] |
| Month / year | 30 days (720 h) / 365 days | assignment convention |
| Fleet | 100 machines, 24×7 | scenario |
| Regions | AWS ap-south-1 (Mumbai), Azure Central India (Pune), GCP asia-south1 (Mumbai) | GCP India prices not retrievable, so default-region list prices are used [S73]–[S76] |
| Message pattern | 1 MQTT message per machine per second (edge batching), except S0 | Part A |
| Payload sizes | measured JSON: 10 sensors at 1 Hz = 296 B; 100 samples at 100 Hz = 729 B; one reading = 125 B; 42 edge features ≈ 564 B; 2 kHz × 3 axes ≈ 42 KB | Part A (`part_a_mqtt_payloads.json`) |
| Storage | 12-month rolling retention in the data lake; Parquet+Zstd compression 6.9× (measured on real UMich signals), 5× for 2 kHz raw (measured on Bosch) | Part A |
| AWS | IoT Core $1.05 per million (tiered), metered in 5 KB units, plus 1 rule and 1 action per message; Kinesis 2 shards; S3 Standard; RDS PostgreSQL db.t4g.medium (Oregon price, Mumbai not retrievable) | [S17][S18][S21][S22][S24] |
| Azure | IoT Hub cheapest tier mix (S1 400k/day $35; S2 6M/day $350; S3 300M/day $3,500; 4 KB metering); Event Hubs 2 TU; ADLS Gen2 Hot; PostgreSQL Flexible B2s | [S46]–[S50] |
| GCP | Pub/Sub $40/TiB plus 3 self-managed MQTT broker VMs (assumption: $60/VM-month); Dataflow 1 worker (**assumption**, $0.07/h); Cloud Storage; Cloud SQL 2 vCPU / 4 GiB. The Manufacturing Connect (Litmus) licence is **not included**: no public price. | [S61][S73]–[S76] |

## Scenarios

| | Data sent to the cloud per machine-second | Messages / month (fleet) |
|---|---|---:|
| **S0** | raw readings, **one MQTT message per reading** (10 × 1 Hz + 100 × 100 Hz) | 28.5 billion |
| **S1** | raw 1 Hz (10 sensors) + raw 100 Hz vibration, batched into 1 message (1,025 B) | 259.2 million |
| **S2** | raw 1 Hz + **42 edge vibration features** (860 B), batched | 259.2 million |
| **S3** | raw 1 Hz + raw **2 kHz tri-axial** accelerometer (42 KB), batched | 259.2 million |

## Results (₹ per month)

| Scenario | AWS | Azure | GCP |
|---|---:|---:|---:|
| S0 one message per reading | ₹29,91,825 | ₹14,25,721 | ₹55,447 |
| S1 raw 1 Hz + raw 100 Hz | ₹43,297 | ₹80,226 | ₹33,216 |
| **S2 raw 1 Hz + edge features (recommended)** | **₹43,121** | **₹80,085** | **₹32,928** |
| S3 raw 2 kHz to the cloud | ₹2,84,788 | ₹3,94,487 | ₹1,19,208 |

Component breakdown: `docs/results/part_c_cost_tables.md`. Figure: `docs/figures/part_c_cost_model.png`.

## What the numbers say

1. **Edge batching is the largest cost lever.**
   - Sending each reading as its own MQTT message (S0) costs ₹14–30 lakh/month on the per-message-priced clouds.
   - Batching one message per machine-second at the gateway (S1) brings that down to ₹0.4–0.8 lakh, **35–70× cheaper**.
2. **At 100 Hz, edge features save bandwidth, not much money.**
   - S1 and S2 cost almost the same, because both payloads fit inside one 4 KB (Azure) or 5 KB (AWS) billing unit and storage is small (~0.5 TB compressed per year).
   - The case for edge processing at 100 Hz rests on latency, outage resilience and data quality (Part G), not on rupees.
3. **At the real sensor rate, edge features save ₹0.9–3.1 lakh per month.**
   - The Bosch accelerometers sample at 2 kHz on 3 axes. Streaming that raw (S3) costs ₹1.2–3.9 lakh/month.
   - Edge features (S2) save **₹2.42 lakh/month on AWS, ₹3.14 lakh on Azure and ₹0.86 lakh on GCP** (₹29–38 lakh/year on AWS/Azure).
   - The 143× reduction measured in Part A is what makes this possible.
4. **Platform ranking for S2:** GCP < AWS < Azure. But:
   - **GCP** excludes the Litmus edge licence that its manufacturing path requires, and relies on assumed broker and Dataflow costs.
   - **Azure**'s bill is dominated by two prepaid IoT Hub S2 units (₹66,300). *Design note (not scored):* Fabric Eventstreams accept MQTT sources directly [S40], and IoT Operations has its own MQTT broker and data flows at the edge [S35]. A path that bypasses IoT Hub is therefore plausible. In that variant Azure S2 would total about ₹13,800/month (Event Hubs + storage + PostgreSQL). It must be validated in a proof-of-concept before it is relied on, so it is **not** used in the scored cost.
5. **The spread between clouds is small in absolute terms.** At ₹33k–80k/month (₹4–10 lakh/year), cloud cost is about 0.7–1.6% of the ₹5.8 crore/year indicative benefit (ML business-impact estimate). Cost is weighted 13%, not more, for that reason.

## One-time edge costs (same for every cloud, assumptions)

| Item | Qty | Indicative ₹ |
|---|---:|---:|
| Industrial PC gateway (fanless, 8-core, 32 GB, 1 TB SSD for store-and-forward), 2 per plant for HA | 6 | 9,00,000 |
| OPC UA enablement on controllers (FASOPC / SINUMERIK OPC UA licence, or edge FOCAS/S7 driver) | 100 | 30,00,000 |
| Vibration sensors + DAQ for spindle monitoring (one tri-axial per machine) | 100 | 35,00,000 |
| Industrial firewall / DMZ switch per plant (IEC 62443 zone boundary) | 3 | 6,00,000 |
| **Total one-time** | | **≈ ₹80 lakh** |
