"""Part F diagrams (PNG + SVG + source) into diagrams/.

  01_linear_flow             required block flow, each block mapped to Azure services + this project's build
  02_reference_architecture  detailed Azure reference architecture with official-style icons (diagrams library)
  03_security_zones          Purdue model / IEC 62443 zones and conduits
  04_er_diagram              ER diagram generated from the live PostgreSQL catalog (falls back to sql/01_schema.sql layout)
  05_data_pipeline           datasets -> scripts -> outputs (real vs benchmark vs derived)
  06_edge_vs_cloud           edge vs cloud split with measured data rates

Needs Graphviz (dot) - default install path is added to PATH automatically.

    python python/make_diagrams.py
"""
from __future__ import annotations

import os
import sys
from html import escape as esc
from pathlib import Path

GV = Path(r"C:\Program Files\Graphviz\bin")
if GV.exists():
    os.environ["PATH"] = str(GV) + os.pathsep + os.environ["PATH"]

import graphviz  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.paths import DIAGRAMS_DIR  # noqa: E402

FONT = "Segoe UI"
BLUE, ORANGE, AQUA, YELLOW, RED, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e34948", "#6250d6"
INK, INK2, MUTED, LINE = "#0b0b0b", "#52514e", "#898781", "#c3c2b7"
OUT = DIAGRAMS_DIR
OUT.mkdir(parents=True, exist_ok=True)


def render(g: graphviz.Digraph, name: str) -> None:
    g.save(OUT / f"{name}.dot")
    for fmt in ("png", "svg"):
        g.render(OUT / name, format=fmt, cleanup=True)
    print("wrote", name)


def base(name: str, rankdir: str = "TB", **graph) -> graphviz.Digraph:
    g = graphviz.Digraph(name, engine="dot")
    g.attr(**{"rankdir": rankdir, "bgcolor": "white", "fontname": FONT, "fontsize": "12", "pad": "0.3", "dpi": "200",
              **graph})
    g.attr("node", fontname=FONT, fontsize="11", color=LINE, penwidth="1.2")
    g.attr("edge", fontname=FONT, fontsize="9.5", color=INK2, arrowsize="0.7", penwidth="1.2")
    return g


# --------------------------------------------------------------------------------------------- 01
def linear_flow() -> None:
    rows = [
        ("CNC / PLC / Sensors", "Fanuc 0i/31i, SINUMERIK 828D/840D sl, spindle accelerometers, 10 streams/machine",
         "Real data: Bosch 2 kHz vibration, UMich 10 Hz spindle; fleet = Azure PdM backbone", "#f3f2ee"),
        ("OPC UA / MQTT", "FASOPC & SINUMERIK OPC UA servers; MQTT 3.1.1/5 with TLS, Unified Namespace topics",
         "tier1/<site>/<area>/<machine>/... topics (paho-mqtt, QoS 1)", "#f3f2ee"),
        ("Edge Gateway", "Azure IoT Operations on Arc-enabled K3s / AKS Edge Essentials: OPC UA connector, MQTT broker, data flows; durable outbox",
         "python/edge: 1-s features (143x reduction), SQLite store-and-forward, 0 lost", "#e6f0fb"),
        ("Cloud Data Ingestion", "Azure IoT Hub (S2) / Event Hubs; Fabric Eventstreams (MQTT source)",
         "amqtt broker + cloud subscriber (persistent session)", "#e6f0fb"),
        ("Data Lake / Time-Series Storage", "ADLS Gen2 (bronze/silver/gold Parquet) + Fabric Eventhouse / Azure Data Explorer (KQL)",
         "data/processed Parquet+Zstd (6.9x measured compression)", "#e6f0fb"),
        ("SQL Database", "Azure Database for PostgreSQL Flexible Server (Central India)",
         "PostgreSQL 16: raw / core / analytics schemas, 876,100-row fact table", "#e6f0fb"),
        ("Python Analytics / AI", "Azure Machine Learning + Fabric notebooks; models registered and scored in batch / at edge",
         "Isolation Forest, gradient boosting, SHAP (python/ml)", "#e6f0fb"),
        ("Dashboard", "Power BI + Fabric Real-Time Dashboards; Streamlit app on Azure App Service",
         "8-page Streamlit dashboard (local Postgres / hosted Parquet)", "#e6f0fb"),
        ("Manufacturing Decision", "Maintenance work orders, tool-change policy, OEE reviews; Teams alerts via Activator",
         "Risk ranking, wear-based tool change: reject 1.50% -> 0.92% (indicative)", "#e9f7f1"),
    ]
    g = base("linear_flow", "TB", nodesep="0.25", ranksep="0.32", label=
             "Part F - Smart-factory data architecture on Microsoft Azure (Central India)\n"
             "left: required block  |  middle: Azure service mapping  |  right: what this project built and measured",
             labelloc="t", fontsize="15")
    import textwrap

    def wrap(s: str, n: int) -> str:
        return '<BR ALIGN="LEFT"/>'.join(esc(x) for x in textwrap.wrap(s, n)) + '<BR ALIGN="LEFT"/>'

    prev = None
    for i, (block, azure, ours, fill) in enumerate(rows):
        label = (f'<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="6" FIXEDSIZE="TRUE" WIDTH="980" HEIGHT="58">'
                 f'<TR><TD WIDTH="200" FIXEDSIZE="TRUE" HEIGHT="50" ALIGN="LEFT"><B><FONT POINT-SIZE="13">{wrap(block, 20)}</FONT></B></TD>'
                 f'<TD WIDTH="430" FIXEDSIZE="TRUE" HEIGHT="50" ALIGN="LEFT" BALIGN="LEFT"><FONT COLOR="{BLUE}">{wrap(azure, 62)}</FONT></TD>'
                 f'<TD WIDTH="350" FIXEDSIZE="TRUE" HEIGHT="50" ALIGN="LEFT" BALIGN="LEFT"><FONT COLOR="{INK2}" POINT-SIZE="10">{wrap(ours, 55)}</FONT></TD>'
                 f'</TR></TABLE>>')
        g.node(f"n{i}", label=label, shape="box", style="rounded,filled", fillcolor=fill, color=LINE, margin="0.05")
        if prev is not None:
            g.edge(prev, f"n{i}", penwidth="2", color=BLUE if i < 8 else AQUA)
        prev = f"n{i}"
    render(g, "01_linear_flow")


# --------------------------------------------------------------------------------------------- 02
def reference_architecture() -> None:
    from diagrams import Cluster, Diagram, Edge
    from diagrams.azure.analytics import AzureDataExplorerClusters, EventHubs, PowerBiEmbedded
    from diagrams.azure.database import DataLake
    from diagrams.azure.databases import AzureDatabasePostgresqlServer
    from diagrams.azure.identity import EntraManagedIdentities
    from diagrams.azure.iot import AzureIotOperations, IotHub
    from diagrams.azure.managementgovernance import Monitor
    from diagrams.azure.ml import MachineLearningServiceWorkspaces
    from diagrams.azure.other import ArcKubernetes, DefenderHmi, DefenderPlc, DefenderSensor, AzureManagedGrafana
    from diagrams.azure.security import KeyVaults, MicrosoftDefenderForIot, Sentinel
    from diagrams.azure.network import Firewall
    from diagrams.azure.compute import FunctionApps
    from diagrams.generic.storage import Storage
    from diagrams.onprem.client import Users

    graph = {"fontname": FONT, "fontsize": "13", "pad": "0.4", "nodesep": "0.45", "ranksep": "0.9", "splines": "spline",
             "dpi": "160"}
    node = {"fontname": FONT, "fontsize": "10"}
    cwd = os.getcwd()
    os.chdir(OUT)
    try:
        with Diagram("Reference architecture - 100 CNC machines, 3 plants, Microsoft Azure Central India",
                     filename="02_reference_architecture", show=False, direction="LR", outformat=["png", "svg"],
                     graph_attr=graph, node_attr=node):
            with Cluster("Plant x3: Chakan (40) | Oragadam (35) | Manesar (25)   [OT zone, Purdue L0-L3]",
                         graph_attr={"bgcolor": "#f6f6f3", "fontname": FONT}):
                with Cluster("L0-L1 machines", graph_attr={"bgcolor": "#ffffff"}):
                    cnc_f = DefenderPlc("Fanuc 0i/31i\n(FASOPC OPC UA)")
                    cnc_s = DefenderPlc("SINUMERIK 828D/840D sl\n(OPC UA option)")
                    acc = DefenderSensor("Spindle accelerometer\n2 kHz x 3 axes")
                with Cluster("L2-L3 edge (industrial PC x2, HA)", graph_attr={"bgcolor": "#e6f0fb"}):
                    aio = AzureIotOperations("IoT Operations\nOPC UA connector\nMQTT broker, data flows")
                    k8s = ArcKubernetes("Arc-enabled K3s\n(AKS Edge Essentials)")
                    buf = Storage("Durable outbox\n7-day store & forward")
                    feat = FunctionApps("Edge features\n1-s RMS/kurtosis/FFT\n143x reduction")
                    hmi = DefenderHmi("Local HMI / alarms\n< 100 ms")
                    graf = AzureManagedGrafana("Plant Grafana\n(offline view)")
                fw_ot = Firewall("L3.5 IDMZ\nfirewall")
            with Cluster("Azure Central India (Pune) - data residency India", graph_attr={"bgcolor": "#fbfbfa", "fontname": FONT}):
                with Cluster("Ingestion", graph_attr={"bgcolor": "#ffffff"}):
                    hub = IotHub("IoT Hub (S2)\ndevice identity, X.509")
                    eh = EventHubs("Event Hubs /\nFabric Eventstreams")
                with Cluster("Storage", graph_attr={"bgcolor": "#ffffff"}):
                    adx = AzureDataExplorerClusters("Fabric Eventhouse / ADX\nhot time series (KQL)")
                    lake = DataLake("ADLS Gen2 lake\nbronze/silver/gold Parquet")
                    pg = AzureDatabasePostgresqlServer("PostgreSQL Flexible\nraw/core/analytics")
                with Cluster("Analytics & AI", graph_attr={"bgcolor": "#ffffff"}):
                    aml = MachineLearningServiceWorkspaces("Azure ML\nanomaly, failure-24h,\ntool-wear models")
                with Cluster("Consumption", graph_attr={"bgcolor": "#ffffff"}):
                    pbi = PowerBiEmbedded("Power BI / Real-Time\nDashboards, OEE")
                with Cluster("Security & operations", graph_attr={"bgcolor": "#fff7e6"}):
                    ent = EntraManagedIdentities("Entra ID +\nmanaged identities")
                    kv = KeyVaults("Key Vault\ncerts & secrets")
                    dfi = MicrosoftDefenderForIot("Defender for IoT\n(local sensor mode)")
                    sen = Sentinel("Sentinel SIEM")
                    mon = Monitor("Azure Monitor")
            users = Users("Plant managers,\nmaintenance, quality")

            [cnc_f, cnc_s] >> Edge(label="OPC UA (4840, TLS)", color=BLUE) >> aio
            acc >> Edge(label="2 kHz raw", color=RED) >> feat
            feat >> Edge(label="42 features/s", color=AQUA) >> aio
            aio - k8s
            aio >> Edge(label="< 100 ms", color=ORANGE) >> hmi
            aio >> graf
            aio >> Edge(style="dashed", label="queue when WAN down") >> buf
            aio >> Edge(label="MQTT/TLS 8883\n~0.69 Mbps fleet", color=BLUE) >> fw_ot
            fw_ot >> Edge(color=BLUE) >> hub
            hub >> eh
            eh >> Edge(label="KQL ingest") >> adx
            eh >> Edge(label="Parquet") >> lake
            adx >> Edge(label="hourly KPIs") >> pg
            lake >> aml
            pg >> aml
            aml >> Edge(style="dashed", label="model to edge (OTA)", color=VIOLET) >> aio
            [pg, adx] >> pbi
            pbi >> Edge(label="decisions: maintenance,\ntool change, OEE", color=AQUA) >> users
            dfi - Edge(style="dotted") - fw_ot
            [ent, kv] - Edge(style="dotted") - hub
            [sen, mon] - Edge(style="dotted") - eh
    finally:
        os.chdir(cwd)
    print("wrote 02_reference_architecture")


# --------------------------------------------------------------------------------------------- 03
def security_zones() -> None:
    g = base("security", "TB", nodesep="0.35", ranksep="0.45", compound="true",
             label="Part F - Security zoning: Purdue model levels and IEC 62443 zones & conduits (one plant shown; same at P1-P3)",
             labelloc="t", fontsize="15")
    def zone(name, label, color, fill, nodes, sl):
        with g.subgraph(name=f"cluster_{name}") as c:
            c.attr(label=f"{label}   [{sl}]", style="rounded,filled", color=color, fillcolor=fill, fontcolor=INK,
                   fontsize="12", penwidth="1.6")
            for nid, txt in nodes:
                c.node(nid, txt, shape="box", style="rounded,filled", fillcolor="white")
    zone("cloud", "Level 5 - Cloud zone: Azure Central India", BLUE, "#eef4fc",
         [("c1", "IoT Hub / Event Hubs\n(X.509 per gateway)"), ("c2", "ADX / ADLS / PostgreSQL\n(private endpoints)"),
          ("c3", "Azure ML, Power BI\n(Entra ID, MFA, RBAC)"), ("c4", "Sentinel, Defender for Cloud,\nKey Vault")], "SL-T 2")
    zone("ent", "Level 4 - Enterprise IT zone", INK2, "#f6f6f3",
         [("e1", "ERP / SAP, MES reports"), ("e2", "Office users, Power BI clients")], "SL-T 2")
    zone("dmz", "Level 3.5 - Industrial DMZ", ORANGE, "#fdf0ea",
         [("d1", "Outbound-only MQTT/TLS relay\n(no inbound from internet)"), ("d2", "Patch / AV / update server"),
          ("d3", "Jump host (MFA, session recording)\nfor vendor remote access")], "SL-T 3")
    zone("ops", "Level 3 - Site operations zone", YELLOW, "#fdf6e3",
         [("o1", "Edge gateway cluster x2\nIoT Operations, OPC UA client,\ndurable outbox (7 days)"),
          ("o2", "Plant historian / local Grafana"), ("o3", "Defender for IoT sensor\n(passive SPAN, local mode)")], "SL-T 3")
    zone("cell", "Levels 0-2 - Cell / machine zone (per shop floor VLAN)", RED, "#fcecec",
         [("m1", "CNC controllers\nFanuc / SINUMERIK\nOPC UA server"), ("m2", "PLC, safety I/O\n(no cloud path)"),
          ("m3", "Accelerometers, DAQ,\nHMI panels")], "SL-T 2-3")
    cons = dict(fontsize="9", color=INK2)
    g.edge("m1", "o1", label=" C1: OPC UA 4840\n Sign&Encrypt, certs", **cons)
    g.edge("m3", "o1", label=" C1: Modbus/TCP, local", **cons)
    g.edge("o1", "d1", label=" C2: MQTT/TLS 8883\n outbound only", color=BLUE, penwidth="1.8", fontsize="9")
    g.edge("d1", "c1", label=" C3: TLS 1.2+ to Azure\n (private peering / VPN)", color=BLUE, penwidth="1.8", fontsize="9")
    g.edge("c3", "e2", label=" C4: HTTPS, Entra ID", **cons)
    g.edge("d3", "o1", label=" C5: RDP/SSH via jump host,\n time-boxed, audited", style="dashed", **cons)
    g.edge("o3", "m1", label=" passive monitoring (SPAN)", style="dotted", dir="back", **cons)
    g.edge("m2", "m1", style="invis")
    g.node("legend", "Rules: no direct traffic L4/L5 -> L0-L2;  all flows initiated from lower to higher level;\n"
                     "deny-by-default firewalls at every conduit;  machine protection and alarms never depend on the cloud.",
           shape="note", fontsize="10", color=LINE, fontcolor=INK2)
    g.edge("e1", "legend", style="invis")
    render(g, "03_security_zones")


# --------------------------------------------------------------------------------------------- 04
SCHEMA_FALLBACK = {
    "core.plant": [("plant_id", "smallint", "PK")], "core.machine": [("machine_id", "smallint", "PK")],
}


def er_diagram() -> None:
    try:
        from utils.db import connect
        with connect() as c:
            cols = c.execute("""
                SELECT table_schema||'.'||table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema IN ('core','edge') ORDER BY table_schema, table_name, ordinal_position""").fetchall()
            keys = c.execute("""
                SELECT tc.table_schema||'.'||tc.table_name, kcu.column_name, tc.constraint_type,
                       ccu.table_schema||'.'||ccu.table_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
                     AND tc.table_schema = kcu.table_schema
                LEFT JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
                     AND tc.constraint_type = 'FOREIGN KEY'
                WHERE tc.table_schema IN ('core','edge') AND tc.constraint_type IN ('PRIMARY KEY','FOREIGN KEY')""").fetchall()
    except Exception as exc:
        print("ER diagram skipped (database not reachable):", exc)
        return
    tables: dict[str, list] = {}
    for t, col, typ in cols:
        tables.setdefault(t, []).append((col, typ))
    pk = {(t, c) for t, c, k, _ in keys if k == "PRIMARY KEY"}
    fk = {(t, c): ref for t, c, k, ref in keys if k == "FOREIGN KEY"}
    g = base("er", "LR", nodesep="0.4", ranksep="1.0", label="Part D - Entity-relationship diagram (generated from the PostgreSQL catalog)",
             labelloc="t", fontsize="15")
    short = {"character varying": "varchar", "timestamp with time zone": "timestamptz", "timestamp without time zone": "timestamp",
             "USER-DEFINED": "enum", "double precision": "float8"}
    for t, cs in tables.items():
        fact = t.endswith("machine_data")
        head = ORANGE if fact else (AQUA if t.startswith("edge") else BLUE)
        rows = "".join(
            f'<TR><TD ALIGN="LEFT" PORT="{c}">{"<B>" if (t, c) in pk else ""}{c}{"</B>" if (t, c) in pk else ""}'
            f'{" 🔑" if (t, c) in pk else ""}{" →" if (t, c) in fk else ""}</TD>'
            f'<TD ALIGN="LEFT"><FONT COLOR="{MUTED}">{short.get(typ, typ)}</FONT></TD></TR>' for c, typ in cs)
        g.node(t, f'<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="3" COLOR="{LINE}">'
                  f'<TR><TD COLSPAN="2" BGCOLOR="{head}"><FONT COLOR="white"><B>{t}</B></FONT></TD></TR>{rows}</TABLE>>',
               shape="plain")
    seen = set()
    for (t, c), ref in fk.items():
        if (t, ref) in seen or ref is None:
            continue
        seen.add((t, ref))
        g.edge(f"{t}:{c}", ref, arrowhead="crow", arrowtail="tee", dir="both", color=INK2)
    render(g, "04_er_diagram")


# --------------------------------------------------------------------------------------------- 05
def data_pipeline() -> None:
    g = base("pipeline", "LR", nodesep="0.3", ranksep="0.6",
             label="Data pipeline - from four public datasets to the PostgreSQL fleet table, models and dashboard",
             labelloc="t", fontsize="15")
    ds = [("bosch", "Bosch CNC Machining\nREAL, 2 kHz, 1,702 files, CC-BY-4.0", BLUE),
          ("umich", "UMich SMART CNC\nREAL, 10 Hz, 18 experiments", BLUE),
          ("azure", "Microsoft Azure PdM\nBENCHMARK (simulated), 876k h", YELLOW),
          ("ai4i", "AI4I 2020\nBENCHMARK (synthetic), 10k rows", YELLOW)]
    with g.subgraph(name="cluster_src") as c:
        c.attr(label="Raw datasets (../raw_datasets, not in repo)", style="rounded", color=LINE)
        for n, l, col in ds:
            c.node(n, l, shape="cylinder", style="filled", fillcolor="white", color=col, penwidth="2")
    steps = [("s00", "00 download\n01 verify"), ("s02", "02 reference\ntables"), ("s03", "03 edge features\n(1-s, 42 values)"),
             ("s04", "04 calibrate\n(temp, current,\nvibration, rejects,\nalarm mapping)"), ("s05", "05 build fleet\ntable"),
             ("s06", "06 load PostgreSQL\n(COPY)"), ("s07", "07 run SQL\n(8 + 10 queries)"), ("ml", "ml/: anomaly,\ntool wear, failure-24h,\nfailure modes, INR impact"),
             ("pa", "Part A volume &\nmeasured compression"), ("pc", "Part C decision\nmatrix & cost model")]
    for n, l in steps:
        g.node(n, l, shape="box", style="rounded,filled", fillcolor="#eef4fc", color=BLUE)
    outs = [("feat", "bosch_features_1s.parquet\n88,536 windows (DERIVED)"), ("fleet", "machine_data.parquet\n876,100 rows (DERIVED)"),
            ("pg", "PostgreSQL\nraw / core / analytics / edge"), ("res", "sql/results, docs/results,\ndocs/figures"),
            ("dash", "Streamlit dashboard\n(Postgres local / Parquet hosted)")]
    for n, l in outs:
        g.node(n, l, shape="note", style="filled", fillcolor="#e9f7f1", color=AQUA)
    for a, b in [("bosch", "s03"), ("s03", "feat"), ("feat", "s04"), ("umich", "s04"), ("ai4i", "s04"), ("azure", "s04"),
                 ("azure", "s05"), ("s02", "s05"), ("s04", "s05"), ("s05", "fleet"), ("fleet", "s06"), ("s06", "pg"),
                 ("pg", "s07"), ("s07", "res"), ("feat", "ml"), ("umich", "ml"), ("azure", "ml"), ("ai4i", "ml"),
                 ("ml", "res"), ("umich", "pa"), ("bosch", "pa"), ("pa", "res"), ("pc", "res"), ("pg", "dash"),
                 ("fleet", "dash"), ("res", "dash"), ("s00", "s02")]:
        g.edge(a, b)
    for n in ("bosch", "umich", "azure", "ai4i"):
        g.edge("s00", n, style="dashed", color=MUTED, arrowhead="none")
    render(g, "05_data_pipeline")


# --------------------------------------------------------------------------------------------- 06
def edge_vs_cloud() -> None:
    g = base("edgecloud", "LR", nodesep="0.25", ranksep="1.2",
             label="Part G - What runs at the edge and what runs in the cloud (numbers measured in this project)",
             labelloc="t", fontsize="15")
    edge_ops = ["High-frequency vibration processing (2 kHz -> 42 features/s)", "Immediate alarms & interlocks (< 100 ms)",
                "Local machine protection (spindle overload stop)", "Noise filtering & data-quality checks",
                "Protocol conversion OPC UA / FOCAS -> MQTT", "Aggregation & batching (1 msg / machine-second)",
                "Store-and-forward during WAN outage (7 days)", "Local HMI / plant Grafana",
                "Model inference at the edge (Isolation Forest)"]
    cloud_ops = ["Historical analysis (876,100 machine-hours)", "Fleet-level analysis & benchmarking (3 plants)",
                 "Long-term storage (data lake, 12+ months)", "AI/ML model development & retraining",
                 "Management dashboards (OEE, quality, alarms)", "OTA model & config updates to gateways",
                 "ERP / MES / SAP integration", "Digital twin & what-if simulation", "Security monitoring (SIEM)"]
    def box(name, title, items, color, fill):
        rows = "".join(f'<TR><TD ALIGN="LEFT">• {esc(i)}</TD></TR>' for i in items)
        g.node(name, f'<<TABLE BORDER="0" CELLSPACING="0" CELLPADDING="5"><TR><TD><B><FONT POINT-SIZE="14" COLOR="{color}">'
                     f'{title}</FONT></B></TD></TR>{rows}</TABLE>>', shape="box", style="rounded,filled", fillcolor=fill,
               color=color, penwidth="2")
    box("edge", "EDGE (plant gateway)", edge_ops, ORANGE, "#fdf0ea")
    box("cloud", "CLOUD (Azure Central India)", cloud_ops, BLUE, "#eef4fc")
    g.edge("edge", "cloud", label="  features + 1 Hz data\n  19.2 -> 0.13 Mbps (fleet vibration)\n  75.7 -> 0.53 TB/year  ",
           color=AQUA, penwidth="3", fontsize="11")
    g.edge("cloud", "edge", label="  models, thresholds,\n  configuration (OTA)  ", color=VIOLET, penwidth="2", style="dashed",
           fontsize="11")
    render(g, "06_edge_vs_cloud")


if __name__ == "__main__":
    linear_flow()
    reference_architecture()
    security_zones()
    er_diagram()
    data_pipeline()
    edge_vs_cloud()
