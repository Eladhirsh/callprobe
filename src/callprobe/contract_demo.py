"""Frozen real-model evidence for the offline contract-comparison tutorial."""
from importlib.resources import files


def generate_contract_demo() -> dict[str, dict[str, str]]:
    root = files("callprobe") / "demo_data" / "contracts"
    groups = {
        "": {name: (root / name).read_bytes().decode("utf-8")
             for name in ("baseline.json", "candidate.json", "DEMO.md")}
    }
    for shape in ("nested", "flat"):
        groups[shape] = {name: (root / shape / name).read_bytes().decode("utf-8")
                         for name in ("suite.yaml", "tools.yaml", "tasks.yaml", "distractors.yaml")}
    return groups
