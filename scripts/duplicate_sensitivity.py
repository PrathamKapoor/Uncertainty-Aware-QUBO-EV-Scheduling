"""Sensitivity of the fixed 90% buffer to full-row duplicates and clustering."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from experiments.public_dataset import prepare_sessions, day_block_interval
from experiments.revised_experiment import reliability_buffer_minutes

frame = pd.read_csv('data/ChargingRecords.csv')
out = {}
for name, data in [('all', frame), ('deduplicated', frame.drop_duplicates().reset_index(drop=True))]:
    samples, counts = prepare_sessions(data)
    cal = [s.delta_d_minutes for s in samples if s.calibration]
    held = [s for s in samples if not s.calibration]
    buffer = reliability_buffer_minutes(cal, .9)
    if not 0 < buffer <= 15:
        raise ValueError('This diagnostic assumes a buffer that retains exactly one slot')
    early = [int(s.delta_d_minutes <= 15) for s in held]
    late = [int(s.delta_d_minutes <= 0) for s in held]
    out[name] = {'counts': counts, 'buffer': buffer,
                 'early_completion': float(np.mean(early)), 'late_completion': float(np.mean(late)),
                 'day_bootstrap': day_block_interval(early, late, [s.block_day for s in held])}
    ids = np.array([int(s.session_id) for s in held])
    users = data.iloc[ids]['UserID'].to_numpy()
    chargers = data.iloc[ids]['ChargerID'].to_numpy()
    known = users != 0
    user_interval = day_block_interval(np.array(early)[known], np.array(late)[known], users[known])
    user_interval['method'] = 'paired user-cluster percentile bootstrap; excludes UserID 0'
    charger_interval = day_block_interval(early, late, chargers)
    charger_interval['method'] = 'paired charger-cluster percentile bootstrap'
    for interval in (user_interval, charger_interval):
        interval['n_clusters'] = interval.pop('n_days')
    out[name]['user_cluster'] = user_interval
    out[name]['charger_cluster'] = charger_interval
Path('artifacts/revised_v2/duplicate_sensitivity.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
print(json.dumps(out, indent=2))
