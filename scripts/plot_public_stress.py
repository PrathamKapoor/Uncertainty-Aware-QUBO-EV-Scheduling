"""Plot actual aggregated outputs from the public-duration stress experiment."""
import gzip
import json
from pathlib import Path

import matplotlib.pyplot as plt

source = Path("artifacts/revised_v2/public_duration_stress.json.gz")
with gzip.open(source, "rt", encoding="utf-8") as f:
    data = json.load(f)
names = list(data["methods"])
rates = [100 * data["methods"][name]["evaluation"]["feasibility_rate"] for name in names]
fig, ax = plt.subplots(figsize=(7, 3.8))
ax.bar(names, rates, color="#286278")
ax.set_ylabel("Simulated service completion (%)")
ax.set_ylim(0, 100)
ax.set_title("Synthetic service targets, observed connection durations")
fig.tight_layout()
fig.savefig("artifacts/revised_v2/public_duration_stress.png", dpi=160)
