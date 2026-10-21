"""Build the scenario reference (master) tables for the 3-plant, 100-machine fleet.

Outputs (data/reference/):
  plant.csv, shop_floor.csv, machine_type.csv, part_master.csv, machine_master.csv

The scenario is an illustrative Automotive Tier-1 supplier in India. Machine
IDs 1-100 are the Azure PdM machineIDs, so every fleet row stays traceable to
its source telemetry. Machine age comes from Azure machines.csv (benchmark);
everything else here is a documented SCENARIO ASSUMPTION, not measured data.

    python python/02_build_reference_tables.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.paths import AZURE_DIR, REFERENCE_DIR  # noqa: E402

SEED = 42

PLANTS = pd.DataFrame([
    # plant_id, code, name, city, state, latitude, longitude, cloud region nearest
    (1, "P1", "Chakan Powertrain Plant", "Chakan, Pune", "Maharashtra", 18.7606, 73.8636),
    (2, "P2", "Oragadam Driveline Plant", "Oragadam, Chennai", "Tamil Nadu", 12.8378, 79.9506),
    (3, "P3", "Manesar Chassis Plant", "Manesar, Gurugram", "Haryana", 28.3540, 76.9366),
], columns=["plant_id", "plant_code", "plant_name", "location", "state", "latitude", "longitude"])
PLANTS["slug"] = ["chakan", "oragadam", "manesar"]

SHOP_FLOORS = pd.DataFrame([
    (1, 1, "powertrain", "Powertrain machining", 1, 40, "Bosch CNC Machining (vibration)"),
    (2, 2, "driveline", "Transmission & driveline", 41, 75, "AI4I 2020 (temperature, torque, tool wear)"),
    (3, 3, "chassis", "Chassis & brakes", 76, 100, "UMich SMART (spindle current, inspection labels)"),
], columns=["shop_floor_id", "plant_id", "slug", "shop_floor_name", "first_machine_id",
            "last_machine_id", "anchoring_real_dataset"])

# Nominal spindle RPM ranges and rated spindle power per machine type (typical
# catalogue ranges for automotive production machines; scenario assumption).
MACHINE_TYPES = pd.DataFrame([
    ("HMC", "Horizontal machining centre", 2000, 8000, 22.0, 415, 0.85),
    ("VMC", "Vertical machining centre", 3000, 10000, 15.0, 415, 0.85),
    ("TURN", "CNC turning centre", 800, 3500, 18.5, 415, 0.85),
    ("HOB", "CNC gear hobbing machine", 300, 1500, 11.0, 415, 0.85),
    ("GRIND", "CNC grinding machine", 1500, 4500, 15.0, 415, 0.85),
], columns=["machine_type", "description", "rpm_min", "rpm_max", "rated_power_kw",
            "supply_voltage_v", "power_factor"])
# Rated line current of the spindle drive: I = P / (sqrt(3) * V * pf)
MACHINE_TYPES["rated_current_a"] = (MACHINE_TYPES.rated_power_kw * 1000
                                    / (np.sqrt(3) * MACHINE_TYPES.supply_voltage_v
                                       * MACHINE_TYPES.power_factor)).round(1)

# Part families with nominal cycle times (minutes per part, scenario assumption)
PARTS = pd.DataFrame([
    (1, "PF01", "Engine block", 1, "HMC", 14.0, 12.0, 18.0, "Cast iron"),
    (2, "PF02", "Cylinder head", 1, "HMC", 7.5, 6.0, 9.0, "Aluminium alloy"),
    (3, "PF03", "Crankcase", 1, "VMC", 11.0, 9.0, 14.0, "Aluminium alloy"),
    (4, "PF04", "Gear shaft", 2, "TURN", 3.5, 3.0, 4.0, "Case-hardening steel"),
    (5, "PF05", "Helical gear", 2, "HOB", 4.5, 3.5, 5.5, "Case-hardening steel"),
    (6, "PF06", "Differential housing", 2, "TURN", 6.0, 5.0, 7.0, "Ductile iron"),
    (7, "PF07", "Gear shaft (finish grind)", 2, "GRIND", 2.5, 2.0, 3.0, "Case-hardening steel"),
    (8, "PF08", "Brake disc", 3, "TURN", 2.0, 1.5, 2.5, "Grey cast iron"),
    (9, "PF09", "Steering knuckle", 3, "VMC", 5.0, 4.0, 6.0, "Ductile iron"),
    (10, "PF10", "Wheel hub", 3, "TURN", 3.0, 2.5, 3.5, "Forged steel"),
], columns=["part_family_id", "part_code", "part_name", "plant_id", "machine_type",
            "cycle_time_min", "cycle_time_low_min", "cycle_time_high_min", "material"])

# Machine-type blocks per plant: (machine_type, count, part_family_id)
LAYOUT = {
    1: [("HMC", 12, 1), ("HMC", 12, 2), ("VMC", 16, 3)],
    2: [("TURN", 10, 4), ("HOB", 10, 5), ("TURN", 5, 6), ("GRIND", 10, 7)],
    3: [("TURN", 9, 8), ("VMC", 8, 9), ("TURN", 8, 10)],
}
CONTROLLERS = ["Fanuc 0i-MF Plus", "Fanuc 31i-B5", "Siemens SINUMERIK 828D", "Siemens SINUMERIK 840D sl"]


def build_machines() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    azure_machines = pd.read_csv(AZURE_DIR / "machines.csv")
    rows, machine_id = [], 1
    for plant_id, blocks in LAYOUT.items():
        plant = PLANTS.set_index("plant_id").loc[plant_id]
        floor = SHOP_FLOORS.set_index("plant_id").loc[plant_id]
        type_counter: dict[str, int] = {}
        for mtype, count, pf in blocks:
            for _ in range(count):
                type_counter[mtype] = type_counter.get(mtype, 0) + 1
                code = f"{mtype.lower()}-{type_counter[mtype]:02d}"
                rows.append({
                    "machine_id": machine_id,
                    "machine_code": f"{plant.plant_code}-{code.upper()}",
                    "plant_id": plant_id,
                    "shop_floor_id": int(floor.shop_floor_id),
                    "machine_type": mtype,
                    "part_family_id": pf,
                    "controller": rng.choice(CONTROLLERS),
                    "uns_topic_root": f"tier1/{plant.slug}/{floor.slug}/{code}",
                })
                machine_id += 1
    m = pd.DataFrame(rows)
    assert len(m) == 100 and m.machine_id.max() == 100
    # Traceability to the Azure PdM benchmark (machineID == machine_id)
    m = m.merge(azure_machines.rename(columns={"machineID": "machine_id", "model": "azure_model",
                                               "age": "age_years"}), on="machine_id", how="left")
    m["commissioning_year"] = 2025 - m["age_years"]
    m = m.merge(MACHINE_TYPES[["machine_type", "rpm_min", "rpm_max", "rated_power_kw", "rated_current_a"]],
                on="machine_type")
    return m.sort_values("machine_id").reset_index(drop=True)


def main() -> None:
    machines = build_machines()
    PLANTS.to_csv(REFERENCE_DIR / "plant.csv", index=False)
    SHOP_FLOORS.to_csv(REFERENCE_DIR / "shop_floor.csv", index=False)
    MACHINE_TYPES.to_csv(REFERENCE_DIR / "machine_type.csv", index=False)
    PARTS.to_csv(REFERENCE_DIR / "part_master.csv", index=False)
    machines.to_csv(REFERENCE_DIR / "machine_master.csv", index=False)
    print(machines.groupby(["plant_id", "machine_type"]).size().rename("machines"))
    print(machines.head(3).to_string(index=False))
    print(f"Wrote reference tables to {REFERENCE_DIR}")


if __name__ == "__main__":
    main()
