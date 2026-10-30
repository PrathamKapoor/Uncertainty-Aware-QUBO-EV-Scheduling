"""Small integer-power QUBO, separate from the frozen historical model.

Power and capacity are integer multiples of a common kW unit. Slack represents
unused capacity, so minimizing over slack gives a one-sided overload penalty.
This implementation is educational and does not certify penalty sufficiency.
"""
from dataclasses import dataclass
import math

import numpy as np
from scheduling.ev_scheduling import QUBO


@dataclass
class RevisedQubo:
    Q: np.ndarray
    c: float
    power: list
    demand: list
    availability: list
    capacity: int
    prices: list
    hours: float
    energy_penalty: float
    capacity_penalty: float
    slack_weights: list
    penalize_unavailable: bool

    @property
    def n(self):
        return self.Q.shape[0]


def build_revised_qubo(power, demand, availability, capacity, prices, hours,
                       energy_penalty, capacity_penalty, *, penalize_unavailable=True):
    """Build symmetric x^T Q x + c; demand is in full-slot counts.

    availability is one bit mask per EV, with bit t indicating slot t.
    Variables include every EV-slot followed by per-slot capacity slack bits.
    """
    if (not power or len(power) != len(demand) or len(power) != len(availability)
            or capacity < 0 or int(capacity) != capacity or hours <= 0
            or any(p <= 0 or int(p) != p for p in power)):
        raise ValueError("integer positive powers and nonnegative integer capacity required")
    N, T = len(power), len(prices)
    weights = [2 ** j for j in range(math.ceil(math.log2(capacity + 1)))] if capacity else []
    n = N * T + T * len(weights)
    Q = np.zeros((n, n))
    c = 0.0

    def square(v, target, coefficient):
        nonlocal c
        Q[:] += coefficient * np.outer(v, v)
        Q[np.diag_indices(n)] -= 2 * coefficient * target * v
        c += coefficient * target ** 2

    for i in range(N):
        v = np.zeros(n)
        for t in range(T):
            k = i * T + t
            available = bool(availability[i] & (1 << t))
            v[k] = int(available)
            Q[k, k] += prices[t] * power[i] * hours * available
            if not available and penalize_unavailable:
                Q[k, k] += energy_penalty
        square(v, demand[i], energy_penalty)
    for t in range(T):
        v = np.zeros(n)
        for i in range(N):
            v[i * T + t] = power[i] * bool(availability[i] & (1 << t))
        for j, w in enumerate(weights):
            v[N * T + t * len(weights) + j] = w
        square(v, capacity, capacity_penalty)
    return RevisedQubo(Q, c, list(power), list(demand), list(availability), capacity,
                       list(prices), hours, energy_penalty, capacity_penalty, weights, penalize_unavailable)


def physical_objective(model, bits):
    N, T = len(model.power), len(model.prices)
    x = np.asarray(bits)
    cost = sum(model.prices[t] * model.power[i] * model.hours * x[i*T+t]
               * bool(model.availability[i] & (1 << t))
               for i in range(N) for t in range(T))
    energy = sum((sum(x[i*T+t] for t in range(T) if model.availability[i] & (1 << t)) - model.demand[i]) ** 2
                 + model.penalize_unavailable * sum(x[i*T+t] for t in range(T) if not model.availability[i] & (1 << t))
                 for i in range(N))
    cap = 0.0
    for t in range(T):
        load = sum(model.power[i] * x[i*T+t] * bool(model.availability[i] & (1 << t)) for i in range(N))
        slack = sum(w * x[N*T+t*len(model.slack_weights)+j]
                    for j, w in enumerate(model.slack_weights))
        cap += (load + slack - model.capacity) ** 2
    return float(cost + model.energy_penalty * energy + model.capacity_penalty * cap)


def average_scenario_qubos(models, frequencies, mode):
    """Average matching QUBOs with a shared slack register.

    This shared-slack model is not recourse. For differing scenario loads use
    scenario_qubo_with_recourse instead.
    """
    if not models or len(models) != len(frequencies) or mode not in ("uniform", "empirical"):
        raise ValueError("invalid scenarios or weighting mode")
    first = models[0]
    if any((m.n, m.power, len(m.prices), m.slack_weights) !=
           (first.n, first.power, len(first.prices), first.slack_weights) for m in models):
        raise ValueError("scenario variables must share the same ordering")
    weights = np.asarray(frequencies, dtype=float)
    if not np.all(np.isfinite(weights)) or np.any(weights < 0) or weights.sum() <= 0:
        raise ValueError("frequencies must be finite, nonnegative and have positive sum")
    weights = np.ones(len(models)) if mode == "uniform" else weights
    weights = weights / weights.sum()
    matrix = sum(w * m.Q for w, m in zip(weights, models))
    constant = sum(w * m.c for w, m in zip(weights, models))
    return QUBO(matrix, float(constant), {(0, i): i for i in range(models[0].n)},
                {"weighting": mode, "weights": weights.tolist()})


def scenario_qubo_with_recourse(models, frequencies, mode):
    """Share charging decisions, but allocate independent slack per scenario."""
    weighted = average_scenario_qubos(models, frequencies, mode)
    weights = weighted.description["weights"]
    first = models[0]
    decisions = len(first.power) * len(first.prices)
    slack = first.n - decisions
    size = decisions + len(models) * slack
    Q = np.zeros((size, size))
    c = 0.0
    for s, (weight, model) in enumerate(zip(weights, models)):
        indices = list(range(decisions)) + list(range(decisions + s * slack, decisions + (s + 1) * slack))
        Q[np.ix_(indices, indices)] += weight * model.Q
        c += weight * model.c
    return QUBO(Q, float(c), {(0, i): i for i in range(size)},
                {"weighting": mode, "weights": weights, "scenario_slack": "independent"})
