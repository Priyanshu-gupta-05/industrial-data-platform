# Sources

All sources accessed **2026-10-21**. IDs `[S#]` are cited in `docs/cloud_research_notes.md` and the report.
Official vendor sources are used wherever possible; third-party sources are marked **(third-party)** and are used only where no official page could be read.
"Search index" means the page could not be fetched directly on 2026-10-21 and its content was taken from the web-search result snippet.

## AWS

| ID | Title | Publisher | URL | Supports |
|---|---|---|---|---|
| S1 | AWS IoT Analytics end of support | AWS (docs) | https://docs.aws.amazon.com/iotanalytics/latest/userguide/iotanalytics-end-of-support.html | IoT Analytics end of support 2025-12-15; no new customers from 2024-07-24. Direct fetch returned HTTP 404 on 2026-10-21, so content comes from the search index. |
| S2 | AWS IoT Analytics migration guide | AWS (docs) | https://docs.aws.amazon.com/iotanalytics/latest/userguide/mig-guide.html | Migration path to Kinesis Data Streams / Data Firehose + Glue + Athena (search index). |
| S3 | AWS IoT Events end of support | AWS (docs) | https://docs.aws.amazon.com/iotevents/latest/developerguide/iotevents-end-of-support.html | IoT Events end of support 2026-05-20; no new customers from 2025-05-20. Direct fetch returned HTTP 404, so content comes from the search index. |
| S4 | AWS IoT Events product page | AWS | https://aws.amazon.com/iot-events/ | Now serves a generic AWS IoT overview that no longer lists IoT Events (fetched). |
| S5 | AWS IoT Analytics product page | AWS | https://aws.amazon.com/iot-analytics/ | Now serves a generic AWS IoT overview that lists IoT Core, Greengrass, SiteWise and others but not IoT Analytics (fetched). |
| S6 | Amazon Timestream for LiveAnalytics availability change | AWS (docs) | https://docs.aws.amazon.com/timestream/latest/developerguide/AmazonTimestreamForLiveAnalytics-availability-change.html | Closed to new customers from 2025-06-20; recommends Timestream for InfluxDB. |
| S7 | What is Timestream for InfluxDB? | AWS (docs) | https://docs.aws.amazon.com/timestream/latest/developerguide/timestream-for-influxdb.html | Managed InfluxDB (2.x branch); available in ap-south-1; instance classes; billing. |
| S8 | AWS IoT SiteWise Monitor availability change | AWS (docs) | https://docs.aws.amazon.com/iot-sitewise/latest/appguide/iotsitewise-monitor-availability-change.html | SiteWise Monitor in maintenance mode and closed to new customers; migrate to Amazon Managed Grafana. |
| S9 | Data processing pack availability change | AWS (docs) | https://docs.aws.amazon.com/iot-sitewise/latest/userguide/iotsitewise-dpp-availability-change.html | SiteWise Edge Data Processing Pack in maintenance mode and closed to new customers; the data collection pack continues; MQTT-enabled V3 gateways are recommended. |
| S10 | Use AWS IoT SiteWise Edge gateways | AWS (docs) | https://docs.aws.amazon.com/iot-sitewise/latest/userguide/gateways.html | SiteWise Edge runs on Greengrass V2 or Siemens Industrial Edge, supports OPC UA and MQTT, and keeps working offline. |
| S11 | SiteWise Edge gateway partner data source options | AWS (docs) | https://docs.aws.amazon.com/iot-sitewise/latest/userguide/connect-partner-data-source.html | Partner sources: CloudRail, EasyEdge, Litmus Edge. |
| S12 | AWS IoT Greengrass V1 maintenance policy | AWS (docs) | https://docs.aws.amazon.com/greengrass/v1/developerguide/maintenance-policy.html | Banner: V1 end of support 2026-10-07. Body text: extended life phase since 2023-06-30. |
| S13 | AWS IoT Greengrass V2 endpoints and quotas | AWS (docs) | https://docs.aws.amazon.com/general/latest/gr/greengrassv2.html | Greengrass V2 is in ap-south-1; ap-south-2 is not listed. |
| S14 | AWS IoT SiteWise endpoints and quotas | AWS (docs) | https://docs.aws.amazon.com/general/latest/gr/iot-sitewise.html | SiteWise is in ap-south-1; ap-south-2 is not listed. |
| S15 | AWS IoT Core endpoints and quotas | AWS (docs) | https://docs.aws.amazon.com/general/latest/gr/iot-core.html | IoT Core control plane, data plane and credential endpoints in ap-south-1; ap-south-2 not found. |
| S16 | AWS Regions | AWS (docs) | https://docs.aws.amazon.com/global-infrastructure/latest/regions/aws-regions.html | ap-south-1 Mumbai (3 AZs, enabled by default) and ap-south-2 Hyderabad (3 AZs, opt-in). |
| S17 | AWS IoT Core pricing | AWS | https://aws.amazon.com/iot-core/pricing/ | Messages metered in 5 KB increments (128 KB maximum); rules and actions also metered in 5 KB increments. |
| S18 | AWS Price List API – AWSIoT, ap-south-1 | AWS | https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSIoT/current/ap-south-1/index.json | Mumbai IoT Core prices for messaging, connectivity, rules and shadow (published 2026-10-03). |
| S19 | AWS IoT SiteWise pricing | AWS | https://aws.amazon.com/iot-sitewise/pricing/ | Metering rules; Edge Data Collection Pack is free and the Data Processing Pack is $200 per gateway per month; US East example prices. |
| S20 | AWS Price List API – AWSIoTSiteWise, ap-south-1 | AWS | https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSIoTSiteWise/current/ap-south-1/index.json | Mumbai SiteWise prices for ingestion, storage, compute and query (published 2026-09-11). |
| S21 | AWS Price List API – AmazonS3, ap-south-1 | AWS | https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonS3/current/ap-south-1/index.json | Mumbai S3 Standard storage tiers (published 2026-10-15). |
| S22 | AWS Price List API – AmazonKinesis, ap-south-1 | AWS | https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonKinesis/current/ap-south-1/index.json | Mumbai Kinesis Data Streams prices (published 2026-09-11). |
| S23 | Amazon RDS for PostgreSQL pricing | AWS | https://aws.amazon.com/rds/postgresql/pricing/ | Price tables are rendered dynamically and could not be read; T4g/T3 CPU credits are $0.075 per vCPU-hour. |
| S24 | RDS PostgreSQL on-demand price map (pricing-page data file) | AWS | https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/rds/USD/current/rds-postgresql-ondemand.json | US West (Oregon) db.t4g.micro and db.t4g.medium hourly prices. The Mumbai rows sit beyond the readable part of the 10 MB file. |
| S25 | Compliance validation for AWS IoT SiteWise | AWS (docs) | https://docs.aws.amazon.com/iot-sitewise/latest/userguide/compliance-validation.html | SiteWise is not in scope of any AWS compliance program (search index). |
| S26 | AWS joins the ISA program in support of the global ISA/IEC 62443 standards | ISA | https://www.isa.org/news-press-releases/2022/july/aws-joins-the-isa-program-in-support-of-the-global | AWS became an ISASecure (ISCI) member in 2022. This is a membership, not a product certification. |
| S27 | Amazon AppFlow SAP OData connector | AWS (docs) | https://docs.aws.amazon.com/appflow/latest/userguide/sapodata.html | SAP S/4HANA and ECC integration via OData and ODP (search index). |

## Microsoft Azure

| ID | Title | Publisher | URL | Supports |
|---|---|---|---|---|
| S28 | Migrating to Real-Time Intelligence in Microsoft Fabric (TSI, archived) | Microsoft Learn | https://learn.microsoft.com/en-us/previous-versions/azure/time-series-insights/migration-to-fabric | Time Series Insights retired 2024-07-07; migrate to Eventhouse or ADX. |
| S29 | What is Azure IoT Central | Microsoft Learn | https://learn.microsoft.com/en-us/azure/iot-central/core/overview-iot-central | Product overview (ms.date 2025-05-09). No retirement banner on the page. |
| S30 | AZ569914 – Retirement: Azure IoT Central will be retired on September 20, 2029 | mc.merill.net (third-party mirror of Azure Updates) | https://mc.merill.net/message/AZ569914 | IoT Central retirement on 2029-09-20 (published 2026-09-29); successor is IoT Hub + DPS + Azure Device Registry. |
| S31 | Azure Updates entry id 569914 | Microsoft | https://azure.microsoft.com/updates?id=569914 | Official URL linked from S30. When fetched it showed "0 Updates found", so it could not be confirmed directly. |
| S32 | Azure IoT Operations versions, support, and licensing | Microsoft Learn | https://learn.microsoft.com/en-us/azure/iot-operations/overview-support | GA versions 1.4.x, 1.3.x and 1.2.x; supported Kubernetes platforms; Arc regions (none in India). |
| S33 | What is the connector for OPC UA? (Azure IoT Operations) | Microsoft Learn | https://learn.microsoft.com/en-us/azure/iot-operations/discover-manage-assets/overview-opc-ua-connector | OPC UA connector features, security, HA and write-back. |
| S34 | Production deployment guidelines – Azure IoT Operations | Microsoft Learn | https://learn.microsoft.com/en-us/azure/iot-operations/deploy-iot-ops/concept-production-guidelines | AIO can run offline for at most 72 hours; disk sizing for offline caching; production PKI for OPC UA. |
| S35 | Disk-backed message buffer for the Azure IoT Operations MQTT broker | Microsoft Learn | https://learn.microsoft.com/en-us/azure/iot-operations/manage-mqtt-broker/howto-disk-backed-message-buffer | Buffer is disabled by default, fixed at deployment, and not durable across pod exit (search index). |
| S36 | IoT Edge supported platforms | Microsoft Learn | https://learn.microsoft.com/en-us/azure/iot-edge/support | 1.6 LTS (end of support 2028-11-14), 1.5 LTS (end of support 2026-11-10), 1.4 end of life 2024-11-12. |
| S37 | Operate Azure IoT Edge devices offline | Microsoft Learn | https://learn.microsoft.com/en-us/azure/iot-edge/offline-capabilities | edgeHub store-and-forward; TTL default 7,200 s; indefinite offline operation. |
| S38 | MQTT broker feature overview (Azure Event Grid) | Microsoft Learn | https://learn.microsoft.com/azure/event-grid/mqtt-overview | Event Grid MQTT broker scenarios (search index). |
| S39 | MQTT broker feature, PubSub capabilities now available for Azure Event Grid | Microsoft Azure Updates | https://azure.microsoft.com/updates/mqtt-broker-feature-pubsub-capabilities-now-available-for-azure-event-grid/ | Event Grid MQTT broker GA in Nov 2023, MQTT v3.1.1 and v5 (search index). |
| S40 | What Is Real-Time Intelligence in Microsoft Fabric? | Microsoft Learn | https://learn.microsoft.com/en-us/fabric/real-time-intelligence/overview | Eventstreams (MQTT and IoT Hub sources), Eventhouse, Activator, Power BI; digital twin builder in preview. |
| S41 | Exciting News: Eventhouse is Now Generally Available! | Microsoft Fabric Blog | https://blog.fabric.microsoft.com/en/blog/exciting-news-eventhouse-is-now-generally-available | Eventhouse GA (search index; post date not confirmed). |
| S42 | What is Azure Data Explorer? | Microsoft Learn | https://learn.microsoft.com/en-us/azure/data-explorer/data-explorer-overview | ADX active (ms.date 2026-07-23) with no retirement notice; time-series and ML functions; Power BI and Grafana connectors. |
| S43 | List of Azure regions | Microsoft Learn | https://learn.microsoft.com/en-us/azure/reliability/regions-list | India regions, their AZs and pairs, including India South Central (Hyderabad). |
| S44 | Microsoft's newest India datacenter region goes live | Microsoft News | https://news.microsoft.com/source/asia/features/microsofts-newest-india-datacenter-region-goes-live-to-power-the-countrys-ai-economy-and-enable-frontier-firms/ | India South Central (Hyderabad) went live in Aug 2026 (search index). |
| S45 | Reliability in Azure IoT Hub | Microsoft Learn | https://learn.microsoft.com/en-us/azure/reliability/reliability-iot-hub | Central India has zone redundancy for compute only; data stays in the geography except for Brazil South and SE Asia. |
| S46 | Azure IoT Hub pricing | Microsoft | https://azure.microsoft.com/en-us/pricing/details/iot-hub/ | Messages per day per unit and 4 KB metering (0.5 KB on the Free tier). Prices show as placeholders. |
| S47 | Azure Retail Prices API – IoT Hub, centralindia | Microsoft | https://prices.azure.com/api/retail/prices?$filter=serviceName eq 'IoT Hub' and armRegionName eq 'centralindia' | IoT Hub unit prices in Central India. |
| S48 | Azure Retail Prices API – Event Hubs, centralindia | Microsoft | https://prices.azure.com/api/retail/prices?$filter=serviceName eq 'Event Hubs' and armRegionName eq 'centralindia' | Event Hubs prices in Central India. |
| S49 | Azure Retail Prices API – ADLS Gen2 Hot LRS, centralindia | Microsoft | https://prices.azure.com/api/retail/prices?$filter=armRegionName eq 'centralindia' and productName eq 'Azure Data Lake Storage Gen2 Hierarchical Namespace' and skuName eq 'Hot LRS' | ADLS Gen2 Hot LRS prices in Central India. |
| S50 | Azure Retail Prices API – Azure Database for PostgreSQL, centralindia | Microsoft | https://prices.azure.com/api/retail/prices?$filter=serviceName eq 'Azure Database for PostgreSQL' and armRegionName eq 'centralindia' and priceType eq 'Consumption' | PostgreSQL Flexible Server compute and storage prices. |
| S51 | Azure Retail Prices API – Azure Data Explorer, centralindia | Microsoft | https://prices.azure.com/api/retail/prices?$filter=serviceName eq 'Azure Data Explorer' and armRegionName eq 'centralindia' and priceType eq 'Consumption' | ADX engine markup only (VM compute is billed separately). |
| S52 | Azure Retail Prices API – Microsoft Fabric capacity usage CU, centralindia | Microsoft | https://prices.azure.com/api/retail/prices?$filter=serviceName eq 'Microsoft Fabric' and armRegionName eq 'centralindia' and contains(meterName, 'Capacity Usage CU') | Fabric CU-hour rate ($0.20) in Central India. |
| S53 | Azure Retail Prices API – Fabric Capacity reservation, centralindia | Microsoft | https://prices.azure.com/api/retail/prices?$filter=serviceName eq 'Microsoft Fabric' and armRegionName eq 'centralindia' and skuName eq 'Fabric Capacity' | Fabric reservation prices (1-year and 3-year). |
| S54 | Microsoft Fabric pricing | Microsoft | https://azure.microsoft.com/en-us/pricing/details/microsoft-fabric/ | F-SKU prices are dynamic placeholders ("$-") and not retrievable. |
| S55 | Enhance your OT security with Defender for IoT | Microsoft Learn | https://learn.microsoft.com/en-us/azure/defender-for-iot/organizations/overview | Agentless OT monitoring; air-gapped/hybrid options; non-European traffic routed to East US. |
| S56 | What's new in Microsoft Defender for IoT | Microsoft Learn | https://learn.microsoft.com/en-us/azure/defender-for-iot/organizations/whats-new | On-premises management console retired 2025-01-01; sensor 26.1.1 released Jun 2026 (search index). |
| S57 | Mirroring SAP (Microsoft Fabric) | Microsoft Learn | https://learn.microsoft.com/en-us/fabric/mirroring/sap | SAP mirroring via SAP Datasphere (preview) (search index). |

## Google Cloud

| ID | Title | Publisher | URL | Supports |
|---|---|---|---|---|
| S58 | Cloud IoT Core (archived product page, Jan 2023) | Google Cloud via Internet Archive | https://web.archive.org/web/20230103220349/https://cloud.google.com/iot-core | IoT Core retirement on 2023-08-16; partner migration (search index; direct fetch failed). |
| S59 | Google Cloud to shut down IoT Core service next year | RCR Wireless (third-party) | https://www.rcrwireless.com/20220816/internet-of-things/google-cloud-to-shut-down-iot-core-service-next-year | Retirement announcement in Aug 2022; Device Manager APIs inaccessible after 2023-08-16 (search index). |
| S60 | Connected device architectures on Google Cloud | Google Cloud (docs) | https://docs.cloud.google.com/architecture/connected-devices | Three patterns (MQTT broker, IoT platform, device to Pub/Sub) with scale comparison. |
| S61 | Standalone MQTT broker architecture on Google Cloud | Google Cloud (docs) | https://docs.cloud.google.com/architecture/connected-devices/mqtt-broker-architecture | Broker on GCE/GKE behind Cloud Load Balancing; Pub/Sub or Dataflow integration. No vendor named. |
| S62 | IoT platform product architecture on Google Cloud | Google Cloud (docs) | https://docs.cloud.google.com/architecture/connected-devices/iot-platform-product-architecture | Third-party IoT platform pattern; the IoT Core URL now redirects here. |
| S63 | Manufacturing Connect | Google Cloud (docs) | https://docs.cloud.google.com/manufacturing-data-engine/docs/concepts/manufacturing-connect | Litmus-built edge; sold and supported by Litmus; 270+ protocols including OPC UA. |
| S64 | Manufacturing Data Engine overview | Google Cloud (docs) | https://docs.cloud.google.com/manufacturing-data-engine/docs/overview | MDE built on Pub/Sub, Dataflow, BigQuery, Bigtable and GCS; script-deployed; no licence fee. |
| S65 | MQTT for Google Cloud | EMQ (vendor, third-party) | https://emqx.com/en/solutions/mqtt-for-google-cloud | Vendor's claim to be an IoT Core successor with Pub/Sub integration (search index). |
| S66 | HiveMQ GCP Pub/Sub data sheet | HiveMQ (vendor, third-party) | https://hivemq.com/sb-assets/f/243938/x/8b66fab842/hivemq-gcp-pub-sub-data-sheet.pdf | HiveMQ Pub/Sub extension (search index). |
| S67 | Google Distributed Cloud connected overview | Google Cloud (docs) | https://docs.cloud.google.com/distributed-cloud/edge/latest/docs/overview | GKE on Google-certified on-prem servers; v1.13.0 is latest. India availability not stated. |
| S68 | Regions and zones (Compute Engine) | Google Cloud (docs) | https://docs.cloud.google.com/compute/docs/regions-zones | asia-south1 (Mumbai, zones a/b/c) and asia-south2 (Delhi, zones a/b/c). |
| S69 | BigQuery locations | Google Cloud (docs) | https://docs.cloud.google.com/bigquery/docs/locations | BigQuery in asia-south1 and asia-south2. |
| S70 | Dataflow locations | Google Cloud (docs) | https://docs.cloud.google.com/dataflow/docs/resources/locations | Dataflow in asia-south1 and asia-south2. |
| S71 | Cloud SQL for PostgreSQL region availability | Google Cloud (docs) | https://docs.cloud.google.com/sql/docs/postgres/region-availability-overview | Cloud SQL Enterprise edition in asia-south1 and asia-south2. |
| S72 | Restrict Pub/Sub resource locations (message storage policy) | Google Cloud (docs) | https://docs.cloud.google.com/pubsub/docs/resource-location-restriction | Pub/Sub data can be pinned to chosen regions; enforceInTransit option. |
| S73 | Pub/Sub pricing | Google Cloud | https://cloud.google.com/pubsub/pricing | $40 per TiB in all regions; first 10 GiB free; BigQuery and GCS subscriptions $50 per TiB (search index; page is JS-rendered). |
| S74 | Cloud Storage pricing | Google Cloud | https://cloud.google.com/storage/pricing | Standard storage $0.000027397 per GiB-hour, region not stated (search index). The Mumbai row is not retrievable. |
| S75 | BigQuery pricing | Google Cloud | https://cloud.google.com/bigquery/pricing | On-demand query $6.25 per TiB; active logical storage $0.000031507 per GiB-hour (us-central1 example) (search index). |
| S76 | Cloud SQL pricing | Google Cloud | https://cloud.google.com/sql/pricing | Enterprise edition "starting at" $0.0413 per vCPU-hour and $0.007 per GiB-hour, region not stated (search index). |
| S77 | Overview of the BigQuery Connector for SAP | Google Cloud (docs) | https://docs.cloud.google.com/sap/docs/bq-connector/latest/overview | SAP LT Replication Server to BigQuery in near real time (search index). |

## Other

| ID | Title | Publisher | URL | Supports |
|---|---|---|---|---|
| S78 | Reserve Bank of India – home page, Reference Rate | RBI (source FBIL) | https://www.rbi.org.in/home.aspx | 94.7145 INR per 1 USD as at 1:00 pm on 2026-10-21. |
| S79 | SINUMERIK 840D sl / 828D OPC UA configuration manual (08/2019) | Siemens | https://cache.industry.siemens.com/dl/files/643/109772643/att_1001368/v1/840Dsl_828D_OPCUA_config_man_0819_en-US.pdf | SINUMERIK 840D sl/828D "Access MyMachine /OPC UA" licensed option (search index). |
| S80 | FANUC America – CNC communications | FANUC America | https://www.fanucamerica.com/products/cnc/cnc-technology/communications | FASOPC OPC UA/DA server built on FOCAS (search snippet only; the fetched page did not show this text, so treat as uncertain). |
| S81 | Microsoft says it won't be retiring Azure IoT Central after all | TechRadar (third-party) | https://www.techradar.com/pro/microsoft-says-it-wont-be-retiring-azure-iot-central-after-all | The Feb 2024 "retire 2027-03-31" message was withdrawn as an error (search index). |
