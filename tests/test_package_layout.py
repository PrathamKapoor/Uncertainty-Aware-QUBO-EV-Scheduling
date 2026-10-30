"""Public package layout groups the project by responsibility."""
import importlib


def test_functional_package_imports():
    for name in ('scheduling.ev_scheduling', 'scheduling.revised_qubo',
                 'quantum.qaoa', 'uncertainty.uncertainty',
                 'experiments.revised_experiment', 'experiments.multi_ev_study'):
        assert importlib.import_module(name) is not None
