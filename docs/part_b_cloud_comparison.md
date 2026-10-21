# Part B: Cloud platform comparison (AWS vs Microsoft Azure vs Google Cloud)

**Scenario.** An automotive Tier-1 supplier runs 100 brownfield CNC machines (Fanuc and Siemens SINUMERIK controllers) in three plants: P1 Chakan (Pune), P2 Oragadam (Chennai) and P3 Manesar (Gurugram). Each machine produces 10 sensor streams at 1 Hz plus one 2 kHz vibration channel that is reduced at the edge. Part A shows the edge cuts this by 143×.

**What the platform must do.**
1. Read OPC UA data from two controller families.
2. Survive the plants' internet outages without losing data.
3. Keep data in India.
4. Feed a PostgreSQL / analytics / ML / dashboard stack.
5. Be run by a small OT and IT team at a cost that is defensible in INR.

**Method.**
- Facts come from official documentation and pricing pages accessed on 2026-10-21. Each fact is cited as `[S#]` and listed in [`sources.md`](sources.md); detailed notes are in [`cloud_research_notes.md`](cloud_research_notes.md).
- Text marked *Assessment* is engineering judgement, not a sourced fact.

## B.1 Service status check (2026-10-21): what is no longer available

Several IIoT services that older comparisons still recommend have been retired or put into maintenance mode. This design does not use any of them.

| Service | Status | Consequence for this design |
|---|---|---|
| Google Cloud IoT Core | **Retired 2023-08-16** [S58] | GCP has no first-party device-connectivity service. A broker or partner layer is required (B.2) [S60]. |
| Azure Time Series Insights | **Retired 2024-07-07** [S28] | Time-series analytics moves to Azure Data Explorer / Fabric Eventhouse [S28]. |
| Azure IoT Central | GA; **retirement announced for 2029-09-20** [S30] (*not fully confirmed: read via a mirror*) | No new build on IoT Central. Use IoT Hub / IoT Operations instead. |
| AWS IoT Analytics | **End of support 2025-12-15** [S1] | AWS's own migration path is Kinesis + Glue + Athena [S2]. |
| AWS IoT Events | **End of support 2026-05-20** [S3] | Alarm logic must be rebuilt elsewhere (edge rules, Lambda, SiteWise alarms). |
| AWS IoT SiteWise Monitor | **Maintenance mode, closed to new customers 2025-11-07** [S8] | Dashboards move to Amazon Managed Grafana [S8]. |
| AWS SiteWise Edge Data Processing Pack | **Maintenance mode** [S9] | Edge data *collection* continues [S9]; edge processing needs partners or open source [S11]. |
| AWS IoT Greengrass V1 | **End of support 2026-10-07** [S12] | Greengrass V2 only. |
| Amazon Timestream for LiveAnalytics | **Closed to new customers 2025-06-20** [S6] | Timestream for InfluxDB instead [S7]. |
| Azure IoT Edge 1.5 LTS | **End of support 2026-11-10**; 1.6 LTS supported to 2028-11-14 [S36] | Any Azure edge design must target 1.6 LTS or IoT Operations. |
| Microsoft Fabric RTI, Azure IoT Operations, Event Grid MQTT | **GA** [S32][S39][S40] | These are the current Azure building blocks. |

## B.2 How each platform connects the shop floor today

- **AWS.**
  - **Edge:** SiteWise Edge runs on Greengrass V2 or on Siemens Industrial Edge. It reads OPC UA and MQTT, and keeps collecting during internet outages, syncing when the link returns [S10].
  - **Cloud:** IoT Core (MQTT) and SiteWise (asset models, computed metrics, alarms) [S9][S17].
  - **Weakness:** the portfolio around it has thinned (B.1). The team has to assemble dashboards (Grafana), stream processing (Kinesis) and query (Athena) itself.
- **Azure.**
  - **Edge:** Azure IoT Operations (AIO) runs on Arc-enabled Kubernetes at the plant. It provides an OPC UA connector with asset discovery into Azure Device Registry, certificate management, high availability and write-back [S33], plus an MQTT broker and edge data flows [S35].
  - **Cloud:** IoT Hub / Event Grid MQTT [S39][S45], then Fabric Real-Time Intelligence (Eventstreams → Eventhouse → Real-Time Dashboards, Activator) or Azure Data Explorer [S40][S42].
  - **Caveats:** AIO can run offline for **at most 72 h**, and its disk buffer is off by default [S34][S35]. AIO's Arc-connection regions include **no India region**, although cloud resources can still sit in Central India [S32].
- **GCP.**
  - **No first-party IIoT layer.** Google documents three patterns: a self-run MQTT broker on GCE/GKE, a third-party IoT platform, or devices straight to Pub/Sub [S60][S61].
  - **Manufacturing offering:** Manufacturing Connect (MC), which is **built, sold and supported by Litmus** (270+ protocols including OPC UA), plus the Manufacturing Data Engine (MDE), deployed into the customer's own project on Pub/Sub, Dataflow, BigQuery and Bigtable [S63][S64].
  - **Consequence:** the edge is a third-party contract.

**Controller reality, for all three clouds.**
- Fanuc controllers need FANUC's FASOPC OPC server or a FOCAS collector [S80].
- SINUMERIK 840D sl / 828D need the *Access MyMachine / OPC UA* licence [S79].
- So every option needs either per-machine controller licences or an edge product with native FOCAS/S7 drivers [S9][S63].

## B.3 Thirteen-criterion comparison: how each platform serves this factory

| Criterion | AWS | Microsoft Azure | Google Cloud |
|---|---|---|---|
| **Industrial IoT capability** | SiteWise models each CNC as an asset with computed OEE-style metrics and alarms in the cloud [S9]; SiteWise Edge reads OPC UA from the plant network [S10]. Gaps: IoT Events retired [S3], Monitor in maintenance [S8], so P1–P3 alarm rules and dashboards must be rebuilt in other services. | IoT Operations gives a Kubernetes-hosted OPC UA connector with asset discovery, certificates and write-back [S33]. This maps directly to 100 machines on three shop-floor networks, registered once in Azure Device Registry. IoT Central is retiring [S30], so the design avoids it. | No first-party IIoT service since IoT Core retired [S58][S60]. The factory would buy Litmus-based Manufacturing Connect [S63] or run its own broker. Workable, but every plant's connectivity depends on a partner. |
| **Data ingestion** | IoT Core MQTT at $1.05 per million messages, metered in 5 KB steps [S17][S18]. One 1-s batch per machine (≈0.9–1 KB, Part A) is one message, about 259 M messages/month for the fleet. Kinesis for high-rate streams [S22]. | IoT Hub units are prepaid daily quotas (S1: 400k msg/day, 4 KB meter) [S46]. The fleet's 8.64 M batched messages/day need 2 × S2 units (₹66,300/month), a predictable but significant flat price [S47]. Event Hubs / Event Grid MQTT for broker-style fan-in [S39][S48]. | Pub/Sub billed per TiB ($40/TiB) [S73]. Cheap for the edge-reduced stream (~0.5 TB/year), but MQTT termination needs a self-run broker VM or a partner [S61]. |
| **Storage options** | S3 Standard $0.025/GB-month in Mumbai [S21] as the data lake; SiteWise hot/warm tiers [S20]; Timestream for InfluxDB (LiveAnalytics closed to new customers) [S6][S7]. Bosch-style raw archives fit S3 lifecycle tiers. | ADLS Gen2 Hot $0.020/GB-month in Central India [S49]; Eventhouse/ADX for hot time-series with KQL [S40][S42]; OneLake in Fabric [S52]. The lake sits in Pune, about 30 km from P1 Chakan. | Cloud Storage and BigQuery in asia-south1 (Mumbai) and asia-south2 (Delhi, near P3 Manesar) [S69][S74]. MDE lands data in BigQuery / Bigtable [S64]. |
| **Stream processing** | Kinesis Data Streams plus consumers (Lambda / Flink) [S22]; SiteWise computed properties for per-machine metrics [S9]. Rolling OEE or vibration baselines need custom code. | Fabric Eventstreams: no-code filters, windowed aggregation, dedup and routing [S40]; ADX update policies and materialized views [S42]; AIO data flows at the edge [S35]. This covers 1-min OEE and alarm routing without custom services. | Dataflow (Apache Beam) in both India regions [S70]: powerful, but code-first, which is a heavier skill demand for a plant team. |
| **SQL and structured data** | RDS / Aurora PostgreSQL [S23]. Mumbai list price not retrievable [S24]. The schema in `sql/` runs unchanged. | Azure Database for PostgreSQL Flexible Server, priced in Central India (B2s $0.098/h, D2ds_v5 $0.251/h) [S50]. The schema and queries in `sql/` run unchanged. | Cloud SQL for PostgreSQL in asia-south1/2 [S71][S76]; BigQuery for large scans. |
| **Analytics** | Athena / Glue over S3 [S2]; Managed Grafana for SiteWise dashboards [S8]; QuickSight. | KQL anomaly and forecasting functions in ADX/Eventhouse [S42], Real-Time Dashboards, and Power BI native in Fabric [S40]. Plant managers already using Excel/Power BI get dashboards without new tools. | BigQuery, serverless SQL at $6.25/TiB scanned [S75]: the strongest ad-hoc analytics engine for fleet-wide history. |
| **AI/ML tools** | SageMaker (general knowledge); SiteWise Assistant GenAI add-on [S20]. | Azure ML; Fabric notebooks; native anomaly detection in Eventhouse [S40][S42]. The Bosch Isolation Forest and the Azure 24-h failure model (Part ML) can be registered and served from Azure ML. | Vertex AI and BigQuery ML (general knowledge). MDE was designed to feed Vertex AI. Strong for data-science-heavy teams. |
| **Edge computing** | Greengrass V2 + SiteWise Edge with explicit outage buffering [S10][S12]; can run on Siemens Industrial Edge. Edge processing pack in maintenance [S9]. | IoT Operations on Arc-enabled K8s (K3s / AKS Edge Essentials) [S32]; IoT Edge 1.6 LTS [S36]. Needs a small K8s cluster per plant. 72-h offline limit [S34]. | MC (Litmus Edge) [S63]; Google Distributed Cloud connected for on-prem GKE [S67] (India availability unknown). |
| **Security** | X.509 per device in IoT Core; IoT Device Defender (general knowledge). SiteWise is not in scope of AWS compliance programmes [S25]. AWS is an ISASecure member, which is not a product certification [S26]. | AIO uses production PKI for OPC UA (≥2048-bit, SHA-1 rejected), X.509 broker auth, managed identities and signed images [S34]; Defender for IoT gives agentless OT network monitoring, also air-gapped [S55]. Caveat: its cloud-connected mode routes non-EU data to East US [S55]. | Pub/Sub can pin message storage to India regions [S72]; edge security is the partner's (Litmus) responsibility [S63]. |
| **Scalability** | IoT Core tiers past 5 B msg/month [S18]: 10× fleet growth is a pricing-tier event, not a redesign. | IoT Hub S3 unit = 300 M msg/day [S46]; ADX ingests millions of events/s [S42]. 1,000 machines = add units. | Pub/Sub autoscales; brokers rated for "millions" of devices [S60]. |
| **Integration** | OPC UA via SiteWise Edge [S10]; SAP via AppFlow [S27]; Siemens Industrial Edge hosting [S10]. | OPC UA connector [S33]; Power BI / Microsoft 365 native [S40]; SAP via Fabric mirroring (preview) [S57]. *Assessment:* most Indian Tier-1 plants already run Microsoft 365 and Entra ID, so identity, Teams alerts and Excel exports come for free. | OPC UA via MC/Litmus [S63]; strongest SAP-to-analytics path through the BigQuery Connector for SAP (SLT, no licence charge) [S77]. |
| **Ease of use** | *Assessment:* mature consoles, but the IIoT stack is now a set of parts (Grafana + Kinesis + Athena + Lambda) after the retirements [S1][S3][S8]. | *Assessment:* Fabric is SaaS and the most turnkey for Power BI users [S40]; IoT Operations requires Kubernetes and Arc skills [S32], which a plant IT team must learn or buy. | *Assessment:* BigQuery is the simplest analytics service, but the factory must own the broker or buy the edge [S60][S63]. |
| **Indicative cost (INR)** | Per-message pricing [S18]: ≈ **₹43,100/month** for the edge-batched design (S2). Naive one-message-per-reading costs ≈ ₹30 lakh/month, so edge batching is essential (`cost_model.md`). | Prepaid IoT Hub units make the bill predictable but dominant: ≈ **₹80,100/month** (S2), of which ₹66,300 is IoT Hub. A variant that bypasses IoT Hub is ≈ ₹13,800 (not yet validated). | ≈ **₹32,900/month** (S2) using per-TiB Pub/Sub [S73], *excluding* the Litmus edge licence and assuming self-run broker VMs. India list prices not retrievable. |

## B.4 Plant-specific requirements

| Requirement | AWS | Azure | GCP |
|---|---|---|---|
| OPC UA to Fanuc + Siemens at Chakan, Oragadam, Manesar | SiteWise Edge OPC UA [S10]; FOCAS via partners [S11] | IoT Operations OPC UA connector [S33]; FASOPC / SINUMERIK OPC UA licences [S79][S80] | MC / Litmus, 270+ protocols [S63] |
| Store-and-forward during outages (frequent on Indian industrial broadband) | **Strongest documented**: SiteWise Edge keeps collecting and syncs later [S10] | IoT Edge edgeHub queues with configurable TTL [S37]; AIO ≤72 h, buffer not durable by default [S34][S35]. *Mitigation:* our gateway outbox (MQTT demo: 0 messages lost) | Depends on the Litmus edge [S63] |
| India data residency | Mumbai hosts IoT Core, SiteWise, Greengrass [S13]–[S15] | IoT Hub data stays in geography [S45]; caveat: AIO Arc control-plane regions and Defender for IoT cloud mode are outside India [S32][S55] | All data services available in both India regions, storage pinnable [S69]–[S72] |
| Region next to the plants | Mumbai (Hyderabad lacks SiteWise / Greengrass) [S13][S14] | Central India = Pune (P1), South India = Chennai (P2) [S43] | Mumbai and Delhi (P3) [S68] |

## B.5 Summary of the comparison

- **Azure** has the most complete current shop-floor-to-dashboard chain: the OPC UA connector, Eventstreams/Eventhouse and Power BI. It also fits the Microsoft tooling the plants already use. Its weak points are the Kubernetes skills IoT Operations needs, the 72-h offline limit, and two residency caveats.
- **AWS** is strongest on documented edge buffering and Mumbai availability. After four retirements, though, it asks the team to assemble the IIoT stack.
- **GCP** has the best analytics engine (BigQuery) and the cleanest SAP path. It has no first-party IIoT layer, so the plants' connectivity would depend on a partner.

These observations become the scores in the Part C weighted decision matrix.
