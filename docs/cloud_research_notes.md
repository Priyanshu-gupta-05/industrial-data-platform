# Cloud research notes: AWS vs Azure vs GCP for a brownfield CNC data platform

Context: an Indian automotive Tier-1 supplier with 100 brownfield CNC machines (Fanuc and Siemens controllers) across three plants: Chakan (Pune), Oragadam (Chennai) and Manesar (Gurugram).
Data path: CNC/PLC → OPC UA/MQTT → edge gateway → cloud ingestion → data lake / time-series → PostgreSQL → analytics/ML → dashboard.

Research date: **2026-10-21**. Every factual claim is tagged with a `[S#]` from `docs/sources.md`.
Text marked **Assessment** is engineering judgement, not a sourced fact. Text marked **Uncertain** means the sources were incomplete or conflicting.

---

## a. Service status verification

| Service | Status on 2026-10-21 | Key dates / notes |
|---|---|---|
| **Google Cloud IoT Core** | **Retired** | Retired 2023-08-16 [S58]. Retirement was announced Aug 2022; the Device Manager APIs became inaccessible after that date [S59]. The old `cloud.google.com/iot-core` URL now redirects to a generic "IoT platform product architecture" page [S62]. |
| **Azure Time Series Insights** | **Retired** | Retired on **2024-07-07**; resources not migrated by then were auto-deleted. Gen2 data stays in the customer's storage account. Microsoft's migration target is Fabric RTI Eventhouse or ADX [S28]. |
| **Azure IoT Central** | **GA, retirement announced** | An Azure Updates notice AZ569914, published 2026-09-29, says IoT Central **retires 2029-09-20**. The successor is IoT Hub + DPS + Azure Device Registry, with Fabric for analytics [S30]. **Uncertain:** I read this notice only via a third-party mirror. The official Azure Updates link (id 569914) did not render [S31], and the Learn overview (ms.date 2025-05-09) has no banner [S29]. A Feb 2024 console message giving "2027-03-31" was withdrawn by Microsoft as an error [S81]. **Assessment:** do not start new builds on IoT Central. |
| **AWS IoT Analytics** | **Discontinued** | Closed to new customers 2024-07-24 (accounts created before 2024-07-23 could keep using it); **end of support 2025-12-15** [S1]. The docs page now returns HTTP 404 and the product URL no longer lists the service [S1][S5]. AWS's documented migration path is Kinesis Data Streams / Data Firehose + Glue + Athena [S2]. |
| **AWS IoT Events** | **Discontinued** | Closed to new customers 2025-05-20; **end of support 2026-05-20** [S3]. The product URL no longer lists the service [S4]. |
| **AWS IoT SiteWise** (cloud) | **GA** | Available in ap-south-1 [S14]. **SiteWise Monitor** (portals) is in **maintenance mode** and was closed to new customers from **2025-11-07**; AWS recommends Amazon Managed Grafana [S8]. The Nov 7 date is in the AWS doc text as returned by search; the page fetched directly states the closure but not the date [S8]. |
| **AWS IoT SiteWise Edge** | **GA (data collection); Data Processing Pack in maintenance mode** | Runs on Greengrass V2 or Siemens Industrial Edge, supports OPC UA and MQTT, and keeps collecting data offline [S10]. The **Data Processing Pack is no longer available to new customers** and is in maintenance mode, but the **data collection pack continues** [S9]. AWS recommends "MQTT-enabled, V3 gateways", open source (Node-RED, InfluxDB, Grafana) or partners (CloudRail, EasyEdge, Litmus Edge) [S9][S11]. **Uncertain:** the page gives no closure date for the DPP. |
| **AWS IoT Greengrass** | **V2 GA; V1 end of support** | The V2 Core software is in the "release phase" [S12]. **V1:** the page banner says AWS **discontinues V1 support on 2026-10-07**, after which V1 resources are no longer accessible. V1 had been in the extended-life phase since 2023-06-30 [S12]. **Uncertain:** the page body still says V1 is supported "until further notice"; the banner is newer. |
| **AWS IoT Core** | **GA** | Endpoints exist in ap-south-1 [S15]; Mumbai price list published 2026-10-03 [S18]. |
| **Azure IoT Hub** | **GA** | Central India is supported, with zone redundancy for compute but not for data [S45]. Central India prices exist [S47]. |
| **Azure IoT Operations** | **GA** | Supported GA versions are **1.4.x, 1.3.x and 1.2.x**; 1.0.x and 1.1.x (versions 2411 to 2506) have left the support window [S32]. **Assessment:** the first GA was therefore Nov 2024 (version 2411). Runs on Arc-enabled Kubernetes: K3s, AKS Edge Essentials, AKS on Azure Local, VKS, RKE2 or OpenShift [S32]. |
| **Azure IoT Edge** | **GA (1.6 LTS)** | **1.6 LTS** released Jul 2026, end of support **2028-11-14**. **1.5 LTS end of support 2026-11-10**, three weeks from today. 1.4 reached end of life 2024-11-12 [S36]. |
| **Microsoft Fabric Real-Time Intelligence** (Eventstreams, Eventhouse) | **GA (core); some sub-features in preview** | Eventhouse GA was announced on the Fabric blog [S41]. **Uncertain:** the post date was not confirmed. The RTI overview documents Eventstreams (including MQTT v3.1/v3.1.1 and IoT Hub sources), Eventhouse, Activator and Real-Time Dashboards. **Digital twin builder** is marked **preview** [S40]. |
| **Azure Event Grid MQTT broker** | **GA** | GA since Nov 2023, with MQTT v3.1.1 and v5 [S39]. Supports many-to-one telemetry, request/response and routing to Azure services [S38]. |
| **Azure Data Explorer** | **GA** | The overview was updated 2026-07-23 with no retirement notice [S42]. Eventhouse is the SaaS offering of ADX [S28]. |
| **Google Cloud Pub/Sub** | **GA** | Priced at $40 per TiB in all regions [S73]. Messages can be pinned to chosen regions [S72]. |
| **Dataflow** | **GA** | Available in asia-south1 and asia-south2 [S70]. |
| **BigQuery** | **GA** | Available in asia-south1 and asia-south2 [S69]. |
| **Google Distributed Cloud** (edge offerings) | **GA (connected)** | GDC connected runs GKE on Google-certified hardware in the customer's premises; the docs show v1.13.0 as "Latest" [S67]. **Uncertain:** whether GDC connected or appliances are sold or supported in India; the page lists no country availability. GDC air-gapped was not researched. |
| **Amazon Timestream for LiveAnalytics** | **Closed to new customers** | Closed to new customers on **2025-06-20**. Existing workloads are unaffected, and AWS says it continues to invest in the service. New customers are steered to Timestream for InfluxDB [S6]. |
| **Amazon Timestream for InfluxDB** | **GA** | Managed InfluxDB on the 2.x branch, available in ap-south-1 [S7]. **Uncertain:** whether InfluxDB 3 engines are offered; the page fetched describes only 2.x. |

Related status items that affect this design:
- **Microsoft Defender for IoT:** the on-premises management console was retired on 2025-01-01 [S56]. OT sensors are still being released (26.1.1 in Jun 2026) [S56]. Cloud-connected data from non-European regions is routed to **East US** [S55]. **This is an India data-residency concern for the cloud-connected mode.**

---

## b. GCP's replacement for IoT Core: what Google recommends now

1. **No first-party device-connectivity service exists after IoT Core.**
   - Google's Architecture Center offers three patterns [S60]:
     - a **standalone MQTT broker**: millions of devices, inter-device messaging recommended, no fleet management;
     - a **third-party IoT platform product**: millions of devices, fleet management recommended;
     - **device directly to Pub/Sub**: hundreds of devices.
   - None of these Architecture Center pages names a broker vendor or mentions IoT Core [S60][S61][S62].
2. **Standalone MQTT broker on GCE or GKE.**
   - Google's reference design is a cluster of three broker instances behind Cloud Load Balancing, with its own credential store and auth service [S61].
   - Data reaches the cloud through broker plugins that publish to Pub/Sub (usually one-way), or through Dataflow / Apache Beam's MQTT IO [S61].
   - EMQX and HiveMQ market Pub/Sub integrations and position themselves as IoT Core successors. These are **vendor claims** [S65][S66].
3. **Manufacturing Data Engine (MDE) + Manufacturing Connect (MC): Google's manufacturing-specific answer.**
   - MC is "designed by Litmus Automation", and is **sold, supported and maintained by Litmus** [S63].
   - MC provides an edge stack with **270+ automation protocols, including OPC UA** [S63].
   - MDE is deployed into the customer's own project by script on **Pub/Sub, Dataflow, BigQuery, Bigtable and Cloud Storage**. MDE has no licence fee; MC is a Marketplace product with an extra cost [S64].
4. **ClearBlade and others:**
   - Google's archived IoT Core page pointed customers to implementation and technology partners for migration [S58].
   - I found no official Google page that names ClearBlade as *the* recommended replacement.
   - **Uncertain:** whether Google currently lists specific partners in a migration guide; the archived page could not be fetched directly.

**Assessment:** for this factory, the realistic GCP path is Litmus Edge / Manufacturing Connect (or another OPC UA-capable edge) → MQTT/Pub/Sub → MDE (BigQuery/Bigtable). The edge layer is then a **third-party product with its own support contract**.

---

## c. Per-cloud capability notes (13 criteria)

Notes on the evidence:
- **Factory-specific facts**:
  - **Fanuc** controllers need either FANUC's **FASOPC** (an OPC UA/DA server built on FOCAS) or a FOCAS-native collector [S80]. **Uncertain:** confirmed only from a search snippet.
  - **Siemens SINUMERIK 840D sl/828D** expose OPC UA through the licensed **Access MyMachine /OPC UA** option [S79].
  - So OPC UA is available on both controller families, but each machine may need a licence. Alternatively, an edge platform with native FOCAS/S7 drivers can be used; Litmus advertises 270+ protocols [S63], and the AWS SiteWise Edge partners advertise 200+ [S9].
- **Text not tagged [S#]:** cells or paragraphs marked **Assessment** are judgement. Most other untagged service names below (for example SageMaker, Azure ML, Vertex AI, Aurora, AlloyDB, RDS Multi-AZ, Pub/Sub autoscaling, Cloud SQL HA) are **general knowledge that was not re-verified on 2026-10-21**.

| # | Criterion | AWS | Azure | GCP |
|---|---|---|---|---|
| 1 | **Industrial IoT capability** | SiteWise asset models, computed properties, alarms and historical queries in the cloud [S9]. SiteWise Edge collects OPC UA/MQTT data [S10]. Monitor portals and the Edge Data Processing Pack are both in maintenance mode [S8][S9]. IoT Analytics and IoT Events are gone [S1][S3]. | Azure IoT Operations: OPC UA connector with asset discovery into Azure Device Registry, write-back and HA [S33]. IoT Hub for device connectivity [S45]. IoT Central is being retired [S30]. | No first-party IIoT service [S60]. MDE + Manufacturing Connect (Litmus) is the manufacturing offering [S63][S64]. |
| 2 | **Ingestion** | IoT Core MQTT/HTTP, metered in 5 KB increments [S17]; Basic Ingest is free [S17]. Kinesis Data Streams [S22]. SiteWise ingestion [S20]. | IoT Hub (4 KB metering, tiered units) [S46]. Event Hubs [S48]. Event Grid MQTT broker [S39]. Fabric Eventstreams take MQTT and IoT Hub sources [S40]. | Pub/Sub at $40/TiB [S73]. The minimum billable message size was not verified. MQTT broker + Pub/Sub plugin or Dataflow [S61]. |
| 3 | **Storage** | S3 Standard, Mumbai tiers [S21]. SiteWise hot and warm tiers, with cold tier in the customer's S3 [S19][S20]. Timestream for InfluxDB (LiveAnalytics is closed to new customers) [S6][S7]. | ADLS Gen2 Hot LRS [S49]. ADX / Fabric Eventhouse for time series [S40][S42]. OneLake hot storage $0.025/GB-month in Central India [S52]. | Cloud Storage [S74]. BigQuery [S75]. Bigtable / BigQuery via MDE [S64]. |
| 4 | **Stream processing** | Kinesis Data Streams [S22]. SiteWise computed properties [S9]. Kinesis + Glue + Athena replaces IoT Analytics [S2]. | Eventstreams processing: filtering, windowed aggregation, dedup, content-based routing [S40]. ADX update policies and materialized views [S42]. AIO data flows at the edge [S35]. | Dataflow (Beam) [S70]. Dataflow is used inside MDE [S64]. |
| 5 | **SQL / managed PostgreSQL** | Amazon RDS for PostgreSQL. Mumbai prices not retrievable; Oregon prices only [S23][S24]. | Azure Database for PostgreSQL Flexible Server, priced in Central India [S50]. | Cloud SQL for PostgreSQL Enterprise edition in asia-south1 and asia-south2 [S71][S76]. |
| 6 | **Analytics** | Athena / Glue (migration target for IoT Analytics) [S2]. Amazon Managed Grafana for SiteWise [S8]. | KQL in ADX / Eventhouse, Real-Time Dashboards, native Power BI [S40][S42]. | BigQuery (on-demand $6.25/TiB) [S75]. |
| 7 | **AI/ML** | SiteWise Assistant (GenAI) is a paid add-on [S19][S20]. | ADX time-series anomaly detection and forecasting [S42]. Eventhouse native anomaly detection; Fabric notebooks for ML [S40]. | BigQuery ML-adjacent analytics on SAP data [S77]. |
| 8 | **Edge** | Greengrass V2 (V1 end of support 2026-10-07) [S12]. SiteWise Edge on Greengrass or Siemens Industrial Edge [S10]. | Azure IoT Operations on Arc-enabled K8s [S32]. IoT Edge 1.6 LTS [S36]. | MC edge (Litmus) [S63]. GDC connected for GKE on-prem [S67]. |
| 9 | **Security** (incl. IEC 62443-relevant) | SiteWise is "not in scope of any AWS compliance programs" [S25]. AWS is an ISASecure (ISA/IEC 62443) **member**, which is not a product certification [S26]. No AWS IEC 62443 product certification was found. | AIO uses production PKI for OPC UA (≥2048-bit keys, SHA-1 rejected), X.509 or SAT auth on the broker, managed identities and signed images [S34]. Defender for IoT gives agentless OT network monitoring and can run air-gapped [S55]. No Azure IEC 62443 certification was found in this pass. | MC/Litmus security is the vendor's responsibility [S63]. Pub/Sub regional pinning [S72]. No IEC 62443 information found for GCP in this pass. |
| 10 | **Scalability** | IoT Core message tiers to more than 5B messages per month [S18]. | IoT Hub units scale to 300M msgs/day per S3 unit [S46]. ADX handles millions of events per second [S42]. | MQTT broker pattern rated at "millions" of devices [S60]. |
| 11 | **Integration** (OPC UA, SAP, MES, M365/Power BI) | OPC UA via SiteWise Edge [S10]. SAP via AppFlow OData/ODP [S27]. | OPC UA connector [S33]. SAP via Fabric mirroring through Datasphere (**preview**) [S57]. Power BI is native in Fabric and ADX [S40][S42]. | OPC UA via MC (Litmus) [S63]. SAP via the BigQuery Connector for SAP (SLT, no charge) [S77]. |
| 12 | **Ease of use** | **Assessment:** AWS IIoT is now fragmented: Monitor and the Edge DPP are in maintenance, Analytics and Events are retired, and teams must assemble Grafana, Kinesis and Athena themselves [S1][S3][S8][S9]. | **Assessment:** AIO requires Kubernetes and Arc operations skills [S32][S34]. Fabric is SaaS and the most turnkey for Power BI users [S40]. | **Assessment:** you must run or buy the broker/edge layer yourself [S60][S61][S63]. BigQuery is simple to operate. |
| 13 | **Indicative cost** | See §e. Mumbai list prices are available from the AWS Price List API [S18][S20][S21][S22]. | See §e. Central India list prices are available from the Azure Retail Prices API [S47]–[S53]. | See §e. India prices could not be retrieved; GCP pages are JS-rendered [S73]–[S76]. |

Untagged general-knowledge service names (not re-verified on 2026-10-21) that complete the table rows above:

| # | Criterion | AWS | Azure | GCP |
|---|---|---|---|---|
| 5 | SQL / PostgreSQL | Aurora PostgreSQL | Flexible Server HA | AlloyDB, Cloud SQL HA |
| 7 | AI/ML | Amazon SageMaker | Azure Machine Learning | Vertex AI (MDE integration was named at its 2022 launch per third-party coverage) |
| 9 | Security | AWS IoT Device Defender | — | — |
| 10 | Scalability | — | — | Pub/Sub autoscaling |
| 11 | MES integration | — | — | MES integration typically through MC/Litmus connectors |

### How each cloud would serve this factory

| Factory requirement | AWS | Azure | GCP |
|---|---|---|---|
| **OPC UA to Fanuc / Siemens** | SiteWise Edge collects OPC UA [S10]. FOCAS or S7 drivers come through a partner (CloudRail, EasyEdge, Litmus Edge) [S11]. SiteWise Edge can run *on* Siemens Industrial Edge [S10]. | AIO OPC UA connector: discovery, certificates, HA, write-back [S33]. It needs FASOPC or SINUMERIK OPC UA licences on the controllers [S79][S80], or a third-party FOCAS collector. | MC (Litmus) with 270+ protocols, including OPC UA [S63]. **Assessment:** Litmus is likely to cover FOCAS natively, but this was not verified on Google's page. |
| **Store-and-forward during internet outages** | SiteWise Edge "continues collecting and processing data during internet outages, syncing with the cloud when connectivity is restored" [S10]. | IoT Edge edgeHub stores upstream messages; TTL defaults to 7,200 s and can be raised; it can run offline indefinitely, limited by TTL and disk [S37]. AIO can run **offline for at most 72 h** [S34]. The AIO disk-backed buffer is off by default and not durable across pod exit [S35]. | Depends on the edge vendor (MC/Litmus). Google's MC page does not describe outage buffering [S63]. **Uncertain.** |
| **India data residency** | Mumbai hosts SiteWise, IoT Core, Greengrass and Timestream for InfluxDB [S7][S13][S14][S15]. Hyderabad (ap-south-2) lacks SiteWise and Greengrass [S13][S14]. | IoT Hub data stays in the geography (exceptions: Brazil South and SE Asia) [S45]. **But** AIO's Arc-connection regions include no India region [S32]. Defender for IoT cloud mode routes to East US [S55]. | Pub/Sub message storage policy can pin data to asia-south1/2 [S72]. BigQuery, Dataflow and Cloud SQL are available in both India regions [S69]–[S71]. |

---

## d. India regions and IoT-service availability

### Region inventory

| Cloud | Region (code) | Location | AZs / zones | Notes |
|---|---|---|---|---|
| AWS | Asia Pacific (Mumbai), `ap-south-1` | India | 3 | Enabled by default [S16] |
| AWS | Asia Pacific (Hyderabad), `ap-south-2` | India | 3 | **Opt-in required** [S16] |
| Azure | Central India, `centralindia` | Pune | 3 | Paired with South India [S43] |
| Azure | South India, `southindia` | Chennai | none | Paired with Central India [S43] |
| Azure | West India, `westindia` | Mumbai | none | Paired with South India [S43] |
| Azure | **India South Central**, `indiasouthcentral` | **Hyderabad** | 3 | Paired with Central India [S43]. Went live Aug 2026 [S44]. |
| GCP | `asia-south1` | Mumbai | 3 (a, b, c) | [S68] |
| GCP | `asia-south2` | Delhi | 3 (a, b, c) | [S68] |

Notes:
- **Uncertain:** the Jio-partnered Azure regions (Jio India West and Jio India Central) do not appear on the Learn regions list fetched today [S43]. Microsoft's news coverage mentions two Jio-partnered datacenters [S44].
- **Assessment:** Azure Central India is in Pune (Chakan plant), Azure South India is in Chennai (Oragadam plant), and GCP asia-south2 is in Delhi (Manesar plant).

### IoT and data services in India regions

| Service | India availability | Source |
|---|---|---|
| AWS IoT Core | ap-south-1: **yes**. ap-south-2: **not found** in the endpoint tables (**Uncertain**). | [S15] |
| AWS IoT SiteWise (+ Edge) | ap-south-1: **yes**. ap-south-2: **no**. | [S14] |
| AWS IoT Greengrass V2 | ap-south-1: **yes**. ap-south-2: **no**. | [S13] |
| Amazon Timestream for InfluxDB | ap-south-1: **yes**. ap-south-2: not listed. | [S7] |
| Kinesis Data Streams, S3 | ap-south-1: priced (therefore available). | [S21][S22] |
| Azure IoT Hub | Central India: **yes**, with AZ redundancy for compute but not data. | [S45][S47] |
| Azure Event Hubs, ADLS Gen2, PostgreSQL Flexible, ADX, Fabric | Central India retail meters exist. **Assessment:** a price meter implies regional availability. | [S48]–[S53] |
| Azure IoT Operations | **No India region in the Arc-connection list**. Supported regions: East US, East US 2, West US, West US 2, West US 3, South Central US, West Europe, North Europe, Germany West Central. The list "doesn't limit you from using your preferred Azure region for cloud resources", so Central India sinks remain possible. | [S32] |
| GCP Pub/Sub | Global service, with storage pinnable to asia-south1/2. | [S72] |
| GCP Dataflow / BigQuery / Cloud SQL PG | asia-south1 and asia-south2: **yes**. | [S69][S70][S71] |
| GCP MDE / MC | Deployed into the customer's own project, so the region is the customer's choice. **Assessment:** inferred from the script-based deployment; MC is a Litmus product. | [S63][S64] |

---

## e. Indicative pricing inputs (USD list price)

### AWS: Asia Pacific (Mumbai), from the AWS Price List API

| Item | Price | Unit | Source |
|---|---|---|---|
| IoT Core messaging, first 1 B msgs/month | **$1.05** | per million messages | [S18] |
| IoT Core messaging, next 4 B | $0.84 | per million messages | [S18] |
| IoT Core messaging, over 5 B | $0.74 | per million messages | [S18] |
| IoT Core message metering | **5 KB increments**, 128 KB max | — | [S17] |
| IoT Core connectivity | $0.092 | per million connection-minutes | [S18] |
| IoT Core rules triggered / actions executed | $0.158 / $0.158 | per million | [S18] |
| IoT Core Device Shadow and Registry operations | $1.31 | per million operations | [S18] |
| SiteWise ingestion | **$1.30** | per million messages | [S20] |
| SiteWise hot storage | $0.00054167 | per GB-hour ($0.013/GB-day; about $0.395/GB-month at 730 h, derived) | [S20] |
| SiteWise warm storage | $0.000054167 | per GB-hour ($0.0013/GB-day; about $0.0395/GB-month, derived) | [S20] |
| SiteWise data processing (computations) | $0.65 | per million computations | [S20] |
| SiteWise warm-tier query | $0.26 | per GB scanned | [S20] |
| SiteWise Edge Data Processing Pack | $200 | per pack (per active gateway per month) | [S19][S20] |
| SiteWise Edge Data Collection Pack | Free | — | [S19] |
| SiteWise metering | Near real-time: 1 KB or 10 data points per message. Buffered: 5 KB or 60 data points. | — | [S19] |
| **S3 Standard** | **$0.025** (first 50 TB), $0.024 (next 450 TB), $0.023 (over 500 TB) | per GB-month | [S21] |
| Kinesis Data Streams, provisioned shard | $0.0175 | per shard-hour | [S22] |
| Kinesis PUT payload units | $0.0185 | per million payload units | [S22] |
| Kinesis on-demand | $0.0517 per stream-hour plus $0.1023 per GB written (Advantage: $0.0409/GB) | — | [S22] |
| **RDS for PostgreSQL** small instance | **Not retrievable for Mumbai** | — | [S23] |
| RDS for PostgreSQL, US West (Oregon) reference | db.t4g.micro $0.016/h; db.t4g.medium $0.065/h | per instance-hour, Single-AZ | [S24] |

### Azure: Central India, from the Azure Retail Prices API

| Item | Price | Unit | Source |
|---|---|---|---|
| IoT Hub **S1** | **$35** | per unit-month; 400,000 msgs/day/unit; 4 KB metering | [S46][S47] |
| IoT Hub **S2** | $350 | per unit-month; 6,000,000 msgs/day/unit; 4 KB | [S46][S47] |
| IoT Hub **S3** | $3,500 | per unit-month; 300,000,000 msgs/day/unit; 4 KB | [S46][S47] |
| IoT Hub B1 / B2 / B3 | $14 / $70 / $700 | per unit-month (same message quotas as S1, S2, S3) | [S46][S47] |
| IoT Hub Free | $0 | 8,000 msgs/day; 0.5 KB metering | [S46][S47] |
| Event Hubs Standard throughput unit | $0.03 | per TU-hour | [S48] |
| Event Hubs Standard ingress | $0.028 | per million events | [S48] |
| Event Hubs Basic TU | $0.015 | per TU-hour | [S48] |
| Event Hubs Premium PU / Dedicated CU | $1.438 / $8.384 | per hour | [S48] |
| Event Hubs Standard Capture | $0.10 | per hour | [S48] |
| **ADLS Gen2 Hot LRS** | **$0.020** (first 50 TB), $0.0192 (next 450 TB), $0.0184 (over 500 TB) | per GB-month | [S49] |
| ADLS Gen2 Hot write / read operations | $0.0715 / $0.0057 | per 10K | [S49] |
| **PostgreSQL Flexible Server B1ms** | **$0.0245** | per hour | [S50] |
| PostgreSQL Flexible Server B2s | $0.098 | per hour | [S50] |
| PostgreSQL Flexible Server D2ds_v5 (General Purpose, 2 vCore) | $0.251 | per hour | [S50] |
| PostgreSQL Flexible Server storage | $0.131 | per GB-month | [S50] |
| ADX Standard engine markup | $0.11 | per hour (markup only; VM compute billed separately) | [S51] |
| Fabric pay-as-you-go CU (Eventhouse, Eventstream, Power BI and others) | **$0.20** | per CU-hour | [S52] |
| Fabric F2 / F4, derived as 2 × $0.20 and 4 × $0.20 | ~$0.40/h (~$292/month) and ~$0.80/h (~$584/month) at 730 h | derived | [S52] |
| Fabric reservation, "Fabric Capacity CU" | $1,042 (1-year) and $3,126 (3-year) | listed "1 Hour" unit | [S53] |
| OneLake hot storage | $0.025 | per GB-month | [S52] |

Caveats for the Azure rows:
- **ADX smallest cluster: not retrievable.** The total cost needs the VM meter for the chosen SKU; only the markup was retrieved [S51].
- **Uncertain:** Fabric F2/F4 are not listed as SKUs in the API, and the Fabric pricing page shows placeholders [S54]. The F2/F4 figures assume F-SKU = n CU × the CU-hour rate.
- **Uncertain:** the Fabric reservation "1 Hour" unit is unclear; it is most likely per CU per term.

### GCP: India prices not retrievable (pages are JS-rendered)

| Item | Price | Unit / region | Source |
|---|---|---|---|
| **Pub/Sub** throughput (message delivery basic) | **$40** | per TiB, **all regions**; first 10 GiB/month free | [S73] |
| Pub/Sub BigQuery / Cloud Storage subscriptions | $50 | per TiB, no free tier | [S73] |
| **Cloud Storage Standard** | $0.000027397 per GiB-hour (≈ $0.02/GiB-month) | **region not stated**; Mumbai not retrievable | [S74] |
| **BigQuery** on-demand query | $6.25 | per TiB (first 1 TiB/month free); region not stated | [S75] |
| BigQuery active logical storage | $0.000031507 per GiB-hour (≈ $0.023/GiB-month) | us-central1 example; Mumbai not retrievable | [S75] |
| **Cloud SQL for PostgreSQL** (Enterprise) | "Starting at" $0.0413 per vCPU-hour + $0.007 per GiB-hour | default/starting region; Mumbai not retrievable | [S76] |

Pages to check for the India rows: https://cloud.google.com/storage/pricing, https://cloud.google.com/bigquery/pricing and https://cloud.google.com/sql/pricing. Select asia-south1 on each.

---

## f. USD → INR exchange rate

**1 USD = ₹94.7145.** This is the RBI/FBIL reference rate as at **1:00 pm IST, 2026-10-21** [S78].
Use it for all INR conversions in the report, and state the date next to every INR figure.

---

## Open uncertainties

1. **Azure IoT Central:** the 2029-09-20 retirement was read via a third-party mirror. The official Azure Updates link did not render [S30][S31].
2. **AWS Greengrass V1:** the page has a conflicting banner and body text about the 2026-10-07 end of support [S12].
3. **SiteWise Edge Data Processing Pack:** the closure date for new customers is not stated [S9].
4. **AWS IoT Core in ap-south-2:** not found in the endpoint tables. Part of the page was unreadable [S15].
5. **Azure IoT Operations has no India Arc region** [S32]. The residency effect needs confirmation from Microsoft.
6. **RDS (Mumbai), ADX cluster total, Fabric F-SKU and all GCP India prices** were not retrievable as exact list figures (see §e).
7. **Fanuc FASOPC OPC UA** is confirmed only from a search snippet [S80].
8. **IEC 62443:** no IEC 62443 certification was found for the relevant service of any of the three clouds [S25][S26].
9. **GDC:** availability in India is unknown [S67].
