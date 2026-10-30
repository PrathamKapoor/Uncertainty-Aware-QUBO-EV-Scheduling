# Worked synthetic example

Run `python scripts/run_revised_quantum_example.py` and `python -m pytest tests/test_revised_qubo.py -q` from the repository root. This is an educational example, not a reconstructed ACN session.

Two EVs each need one 1-hour slot at 1 kW. The site limit is 1 kW. Slot prices are 0.5 and 1 currency unit/kWh. Let the four decisions be `x00, x01, x10, x11`, with binary slack bits `s0, s1` representing unused capacity in kW. In this special example the direct penalized objective is

`0.5(x00+x10) + (x01+x11) + 5[(x00+x01-1)^2 + (x10+x11-1)^2] + 5[(x00+x10+s0-1)^2 + (x01+x11+s1-1)^2]`.

The capacity equality uses slack: a load of zero is allowed with slack one; a load of one uses slack zero. A load of two cannot be repaired by nonnegative slack. In this integer example, minimizing over slack yields a one-sided squared overload penalty. It is a soft constraint: no general guarantee that a fixed penalty makes all optima feasible is claimed.

For `x=(x00,x01,x10,x11,s0,s1)`, `f=xᵀQx+20`, where

```text
Q = [[-9.5,  5,   5,   0,  5,  0],
     [ 5,   -9,   0,   5,  0,  5],
     [ 5,    0, -9.5,  5,  5,  0],
     [ 0,    5,   5,  -9,  0,  5],
     [ 5,    0,   5,   0, -5,  0],
     [ 0,    5,   0,   5,  0, -5]]
```

The symmetric off-diagonal entries contribute twice. For `(1,0,0,1,0,0)`, both EVs receive one slot, each slot has load 1 kW, and the objective is 1.5. Exhaustive enumeration establishes 1.5 as the global QUBO minimum for this example. The alternative swaps the EVs.

Set `x_i=(1-Z_i)/2`. The Ising coefficients implemented by `quantum.qaoa.qubo_to_ising` are `h_i=-sum_j Q_ij/2`, `J_ij=Q_ij/2` for `i<j`, and offset `c+(sum(Q)+trace(Q))/4`. The test checks every one of the 64 basis states, including Qiskit's rightmost-character-is-qubit-zero convention. The actual parameterized circuits are in `artifacts/revised_v2/circuit_p1.txt` and `circuit_p2.txt`; QAOA applies Hadamards, cost evolution and X rotations, then measures. The sampled bitstring is reversed to obtain variable order. Slack bits do not represent EV charging decisions.
