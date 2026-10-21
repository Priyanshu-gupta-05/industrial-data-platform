"""Build report.pdf from docs/report/report.md (reproducible: Markdown -> HTML -> PDF via headless Edge/Chrome).

Macros in report.md
  {{include:docs/x.md|from=## A.1|to=## A.6|shift=1}}   include a section of another document (headings shifted)
  {{csv:sql/results/q2.csv|Caption|max_rows=10|cols=a,b}}  table from a result CSV (numbered caption)
  ![Caption](docs/figures/x.png)                          numbered figure
  Table: Caption                                          (line before a Markdown table) numbered table caption
  [S12], [D1]                                             citations -> IEEE numbers; reference list generated
  [SCREENSHOT: ...]                                       placeholder box for the author's screenshots

    python python/build_report.py
"""
from __future__ import annotations

import html
import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "report" / "report.md"
BUILD = ROOT / "docs" / "report" / "build"
OUT_PDF = ROOT / "report.pdf"
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe"]

DATASET_REFS = {
    "D1": 'M.-A. Tnani, M. Feil, and K. Diepold, "Smart data collection system for brownfield CNC milling machines: '
          'A new benchmark dataset for data-driven machine monitoring," <i>Procedia CIRP</i>, vol. 107, pp. 131-136, 2022. '
          'Dataset: https://github.com/boschresearch/CNC_Machining (CC-BY-4.0).',
    "D2": 'University of Michigan SMART Laboratory, "CNC mill tool wear" dataset, Kaggle (shasun/tool-wear-detection-in-cnc-mill). '
          'Mirror used: https://github.com/flyinginte/toolwear_cncmilling (accessed Oct. 21, 2026).',
    "D3": 'Microsoft, "Predictive maintenance modelling guide" sample data (Azure AI Gallery), Kaggle '
          '(arnabbiswas1/microsoft-azure-predictive-maintenance). Mirror used: https://github.com/avidunixuser/telemetry '
          '(accessed Oct. 21, 2026).',
    "D4": 'S. Matzka, "Explainable artificial intelligence for predictive maintenance applications," in <i>Proc. 3rd Int. '
          'Conf. Artificial Intelligence for Industries (AI4I)</i>, 2020, pp. 69-74. Dataset: UCI Machine Learning Repository '
          'id 601, doi:10.24432/C5HS5C (CC-BY-4.0).',
    "D5": 'ISO 10816-3:2009, "Mechanical vibration - Evaluation of machine vibration by measurements on non-rotating parts - '
          'Part 3: Industrial machines with nominal power above 15 kW," International Organization for Standardization, 2009.',
    "D6": 'IEC 62443-3-3:2013, "Industrial communication networks - Network and system security - Part 3-3: System security '
          'requirements and security levels," International Electrotechnical Commission, 2013.',
}

fig_n = 0
tab_n = 0


def sources() -> dict[str, str]:
    refs = {}
    for line in (ROOT / "docs" / "sources.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(S\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(\S+)\s*\|", line)
        if m:
            sid, title, pub, url = m.groups()
            refs[sid] = f'{html.escape(pub)}, "{html.escape(title)}." [Online]. Available: {html.escape(url)} (accessed Oct. 21, 2026).'
    refs.update(DATASET_REFS)
    return refs


def include(m: re.Match) -> str:
    args = m.group(1).split("|")
    text = (ROOT / args[0]).read_text(encoding="utf-8")
    opts = dict(a.split("=", 1) for a in args[1:])
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if opts.get("from") and l.startswith(opts["from"])), 0)
    end = next((i for i, l in enumerate(lines) if i > start and opts.get("to") and l.startswith(opts["to"])), len(lines))
    body = [l for l in lines[start:end] if not l.startswith("# ")]
    shift = int(opts.get("shift", 1))
    out = [("#" * shift + l) if re.match(r"#{2,5} ", l) else l for l in body]
    return "\n".join(out)


def csv_table(m: re.Match) -> str:
    global tab_n
    parts = m.group(1).split("|")
    df = pd.read_csv(ROOT / parts[0])
    opts = dict(p.split("=", 1) for p in parts[2:])
    if "cols" in opts:
        df = df[opts["cols"].split(",")]
    n = int(opts.get("max_rows", 15))
    note = f" (first {n} of {len(df)} rows)" if len(df) > n else ""
    df = df.head(n)
    tab_n += 1
    cap = f'<p class="cap">Table {tab_n}: {html.escape(parts[1])}{note}. Source: <code>{parts[0]}</code>.</p>'
    fmt = df.apply(lambda c: c.map(lambda v: f"{v:,.3f}".rstrip("0").rstrip(".") if isinstance(v, float) else v))
    return cap + "\n\n" + fmt.to_html(index=False, border=0, classes="data", na_rep="")


def figures(md: str) -> str:
    def rep(m):
        global fig_n
        fig_n += 1
        cap, path = m.group(1), m.group(2)
        cls = ""
        if cap.endswith(" {tall}"):
            cap, cls = cap[:-7], ' class="tall"'
        uri = (ROOT / path).resolve().as_uri()
        return (f'<figure{cls}><img src="{uri}" alt="{html.escape(cap)}"/>'
                f'<figcaption>Figure {fig_n}: {cap}</figcaption></figure>')
    return re.sub(r"^!\[(.+?)\]\((.+?)\)\s*$", rep, md, flags=re.M)


def tables_in_order(md: str) -> str:
    """Number CSV tables and 'Table:' captions in a single pass, in document order."""
    def rep(m):
        global tab_n
        if m.group(1) is not None:
            return csv_table(re.match(r"(.+)", m.group(1)))
        tab_n += 1
        return f'<p class="cap">Table {tab_n}: {m.group(2)}</p>\n'
    return re.sub(r"\{\{csv:(.+?)\}\}|^Table:\s*(.+)$", rep, md, flags=re.M)


def list_spacing(md: str) -> str:
    """Python-Markdown needs a blank line before a list; insert it (outside code fences)."""
    out, fence = [], False
    item = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")
    for line in md.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
        if not fence and item.match(line):
            ind = len(line) - len(line.lstrip(" "))
            if ind:                                   # nested item: Python-Markdown needs 4-space steps
                line = " " * (ind * 2) + line.lstrip(" ")
        if (not fence and item.match(line) and out and out[-1].strip() and not item.match(out[-1])
                and not out[-1].startswith(("    ", "\t")) and not out[-1].lstrip().startswith("|")):
            out.append("")
        out.append(line)
    return "\n".join(out)


def citations(md: str, refs: dict) -> tuple[str, list]:
    order: list[str] = []
    def num(sid):
        if sid not in order:
            order.append(sid)
        return order.index(sid) + 1
    def rep(m):
        ids = re.findall(r"[SD]\d+", m.group(0))
        return "[" + ", ".join(str(num(i)) for i in ids if i in refs) + "]"
    md = re.sub(r"\[[SD]\d+\](?:\s*[-–]\s*\[[SD]\d+\])?", rep, md)
    return md, order


def appendix_tables() -> None:
    """One compact per-machine table combining the per-machine required-query outputs."""
    r = ROOT / "sql" / "results"
    q1 = pd.read_csv(r / "q1_avg_temperature_per_machine.csv")[["machine_code", "plant_code", "avg_temperature_c"]]
    q4 = pd.read_csv(r / "q4_alarm_count_per_machine.csv")[["machine_code", "alarm_events", "alarm_hours"]]
    q7 = pd.read_csv(r / "q7_avg_rpm_while_running.csv")[["machine_code", "machine_type", "avg_rpm_running"]]
    sql_q8 = ("SELECT m.machine_code, SUM(production_count) AS parts, ROUND(100.0*SUM(reject_count)/SUM(production_count),3) "
              "AS rejection_rate_pct FROM core.machine_data JOIN core.machine m USING (machine_id) GROUP BY 1")
    try:
        sys.path.insert(0, str(ROOT / "python"))
        from utils.db import connect
        with connect() as c:
            q8 = pd.DataFrame(c.execute(sql_q8).fetchall(), columns=["machine_code", "parts", "rejection_rate_pct"])
    except Exception:
        md = pd.read_parquet(ROOT / "data" / "processed" / "machine_data.parquet", columns=["machine_id", "production_count", "reject_count"])
        mm = pd.read_csv(ROOT / "data" / "reference" / "machine_master.csv")[["machine_id", "machine_code"]]
        g = md.groupby("machine_id")[["production_count", "reject_count"]].sum().reset_index().merge(mm)
        q8 = pd.DataFrame({"machine_code": g.machine_code, "parts": g.production_count,
                           "rejection_rate_pct": (100 * g.reject_count / g.production_count).round(3)})
    out = q7.merge(q1, on="machine_code").merge(q4, on="machine_code").merge(q8, on="machine_code")
    out = out[["machine_code", "plant_code", "machine_type", "avg_temperature_c", "alarm_events", "alarm_hours",
               "avg_rpm_running", "parts", "rejection_rate_pct"]]
    out.to_csv(ROOT / "docs" / "results" / "appendix_per_machine.csv", index=False)


def build() -> Path:
    global fig_n, tab_n
    fig_n = tab_n = 0
    appendix_tables()
    refs = sources()
    md = SRC.read_text(encoding="utf-8")
    md = re.sub(r"\{\{include:(.+?)\}\}", include, md)
    md = tables_in_order(figures(list_spacing(md)))
    md, order = citations(md, refs)
    md = re.sub(r"\[SCREENSHOT:\s*(.+?)\]", lambda m: f'<div class="shot">[SCREENSHOT: {m.group(1)}]</div>', md)
    md = md.replace("{{REFERENCES}}", "\n".join(
        f'<p class="ref">[{i}] {refs[s]}</p>' for i, s in enumerate(order, 1)))
    body = markdown.markdown(md, extensions=["tables", "toc", "attr_list", "md_in_html", "sane_lists"],
                             extension_configs={"toc": {"toc_depth": "2", "title": ""}})
    css = (ROOT / "docs" / "report" / "report.css").read_text(encoding="utf-8")
    BUILD.mkdir(parents=True, exist_ok=True)
    page = f'<!doctype html><html><head><meta charset="utf-8"><title>Industrial Data Platform - Technical Report</title><style>{css}</style></head><body>{body}</body></html>'
    out = BUILD / "report.html"
    out.write_text(page, encoding="utf-8")
    print(f"HTML: {out}  figures={fig_n} tables={tab_n} references={len(order)}")
    return out


def to_pdf(html_path: Path) -> None:
    exe = next((b for b in BROWSERS if Path(b).exists()), shutil.which("msedge") or shutil.which("chrome"))
    if not exe:
        sys.exit("No Edge/Chrome found to print the PDF")
    subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--run-all-compositor-stages-before-draw",
                    "--virtual-time-budget=20000", f"--print-to-pdf={OUT_PDF}", html_path.as_uri()],
                   check=True, capture_output=True, timeout=180)
    try:
        from pypdf import PdfReader
        print(f"PDF: {OUT_PDF}  pages={len(PdfReader(OUT_PDF).pages)}  size={OUT_PDF.stat().st_size / 1e6:.1f} MB")
    except Exception:
        print(f"PDF: {OUT_PDF}")


if __name__ == "__main__":
    to_pdf(build())
