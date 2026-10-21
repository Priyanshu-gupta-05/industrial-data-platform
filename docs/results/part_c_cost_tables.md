| Scenario | Component | AWS (₹/month) | Azure (₹/month) | GCP (₹/month) |
|---|---|---:|---:|---:|
| S0 raw, one message per reading | Data lake storage (ADLS Gen2 Hot) |  | 11,741 |  |
| S0 raw, one message per reading | Data lake storage (Cloud Storage) |  |  | 11,741 |
| S0 raw, one message per reading | Data lake storage (S3) | 14,677 |  |  |
| S0 raw, one message per reading | Ingestion (IoT Core msgs + rules) | 2,918,975 |  |  |
| S0 raw, one message per reading | Ingestion (IoT Hub S3) |  | 1,326,003 |  |
| S0 raw, one message per reading | Ingestion (Pub/Sub + 3 broker VMs) |  |  | 29,329 |
| S0 raw, one message per reading | PostgreSQL (2 vCPU + 4 GiB + 128 GB) |  |  | 9,603 |
| S0 raw, one message per reading | PostgreSQL (2 vCPU burstable + 128 GB) | 5,827 | 8,271 |  |
| S0 raw, one message per reading | Stream processing (Dataflow, assumed 1 worker) |  |  | 4,774 |
| S0 raw, one message per reading | Stream processing (Event Hubs 2 TU) |  | 79,706 |  |
| S0 raw, one message per reading | Stream processing (Kinesis, 2 shards) | 52,346 |  |  |
| S1 raw 1 Hz + raw 100 Hz | Data lake storage (ADLS Gen2 Hot) |  | 875 |  |
| S1 raw 1 Hz + raw 100 Hz | Data lake storage (Cloud Storage) |  |  | 875 |
| S1 raw 1 Hz + raw 100 Hz | Data lake storage (S3) | 1,094 |  |  |
| S1 raw 1 Hz + raw 100 Hz | Ingestion (IoT Core msgs + rules) | 33,535 |  |  |
| S1 raw 1 Hz + raw 100 Hz | Ingestion (IoT Hub S2) |  | 66,300 |  |
| S1 raw 1 Hz + raw 100 Hz | Ingestion (Pub/Sub + 3 broker VMs) |  |  | 17,964 |
| S1 raw 1 Hz + raw 100 Hz | PostgreSQL (2 vCPU + 4 GiB + 128 GB) |  |  | 9,603 |
| S1 raw 1 Hz + raw 100 Hz | PostgreSQL (2 vCPU burstable + 128 GB) | 5,827 | 8,271 |  |
| S1 raw 1 Hz + raw 100 Hz | Stream processing (Dataflow, assumed 1 worker) |  |  | 4,774 |
| S1 raw 1 Hz + raw 100 Hz | Stream processing (Event Hubs 2 TU) |  | 4,779 |  |
| S1 raw 1 Hz + raw 100 Hz | Stream processing (Kinesis, 2 shards) | 2,841 |  |  |
| S2 raw 1 Hz + edge features | Data lake storage (ADLS Gen2 Hot) |  | 734 |  |
| S2 raw 1 Hz + edge features | Data lake storage (Cloud Storage) |  |  | 734 |
| S2 raw 1 Hz + edge features | Data lake storage (S3) | 918 |  |  |
| S2 raw 1 Hz + edge features | Ingestion (IoT Core msgs + rules) | 33,535 |  |  |
| S2 raw 1 Hz + edge features | Ingestion (IoT Hub S2) |  | 66,300 |  |
| S2 raw 1 Hz + edge features | Ingestion (Pub/Sub + 3 broker VMs) |  |  | 17,817 |
| S2 raw 1 Hz + edge features | PostgreSQL (2 vCPU + 4 GiB + 128 GB) |  |  | 9,603 |
| S2 raw 1 Hz + edge features | PostgreSQL (2 vCPU burstable + 128 GB) | 5,827 | 8,271 |  |
| S2 raw 1 Hz + edge features | Stream processing (Dataflow, assumed 1 worker) |  |  | 4,774 |
| S2 raw 1 Hz + edge features | Stream processing (Event Hubs 2 TU) |  | 4,779 |  |
| S2 raw 1 Hz + edge features | Stream processing (Kinesis, 2 shards) | 2,841 |  |  |
| S3 raw 2 kHz tri-axial | Data lake storage (ADLS Gen2 Hot) |  | 49,936 |  |
| S3 raw 2 kHz tri-axial | Data lake storage (Cloud Storage) |  |  | 49,936 |
| S3 raw 2 kHz tri-axial | Data lake storage (S3) | 62,420 |  |  |
| S3 raw 2 kHz tri-axial | Ingestion (IoT Core msgs + rules) | 213,246 |  |  |
| S3 raw 2 kHz tri-axial | Ingestion (IoT Hub S3) |  | 331,501 |  |
| S3 raw 2 kHz tri-axial | Ingestion (Pub/Sub + 3 broker VMs) |  |  | 54,896 |
| S3 raw 2 kHz tri-axial | PostgreSQL (2 vCPU + 4 GiB + 128 GB) |  |  | 9,603 |
| S3 raw 2 kHz tri-axial | PostgreSQL (2 vCPU burstable + 128 GB) | 5,827 | 8,271 |  |
| S3 raw 2 kHz tri-axial | Stream processing (Dataflow, assumed 1 worker) |  |  | 4,774 |
| S3 raw 2 kHz tri-axial | Stream processing (Event Hubs 2 TU) |  | 4,779 |  |
| S3 raw 2 kHz tri-axial | Stream processing (Kinesis, 2 shards) | 3,295 |  |  |

| Scenario | AWS total | Azure total | GCP total |
|---|---:|---:|---:|
| S0 raw, one message per reading | ₹2,991,825 | ₹1,425,721 | ₹55,447 |
| S1 raw 1 Hz + raw 100 Hz | ₹43,297 | ₹80,226 | ₹33,216 |
| S2 raw 1 Hz + edge features | ₹43,121 | ₹80,085 | ₹32,928 |
| S3 raw 2 kHz tri-axial | ₹284,788 | ₹394,487 | ₹119,208 |