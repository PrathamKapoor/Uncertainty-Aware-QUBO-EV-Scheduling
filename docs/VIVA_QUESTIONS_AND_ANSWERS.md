# Viva questions: revised pilot

1. **Why schedule EV charging?** Vehicles compete for limited electrical capacity and prices vary by time; scheduling selects charging times while attempting to satisfy each request.
2. **Why binary variables?** The pilot assumes a charger is either on at a fixed power or off in each slot. Continuous charging power would require a different encoding.
3. **What is a QUBO?** An objective `xᵀQx+c` for binary `x`. Its quadratic interactions can encode coupled decisions.
4. **Why not solve this classically?** One can and should: enumeration verifies this small instance. QAOA is studied as an exploratory hybrid method, without a speedup claim.
5. **What is a qubit here?** One binary variable, either an EV-slot decision or a capacity slack bit, maps to one qubit.
6. **Why use slack?** `L+s=Pmax`, with nonnegative slack, can represent any allowed unused integer capacity; overload cannot be repaired by slack.
7. **Is the capacity constraint hard?** No. A finite penalty discourages violation; its sufficiency must be established for each instance.
8. **Why might a very large penalty be harmful?** It creates widely different energy scales, potentially making variational parameter optimization difficult.
9. **What does the energy penalty do?** The pilot penalizes squared deviation between delivered slot count and required slot count. It also penalizes commands outside availability.
10. **What units are used?** Power times slot duration is energy: `kWh = kW × h`. Price in currency/kWh times that energy gives currency.
11. **What if a vehicle leaves early?** `realized_availability_mask` counts only complete nominal slots ending by actual departure; `decode_feasibility` uses the same rule.
12. **What if it leaves before arrival?** The effective mask is empty; a positive requirement remains unmet rather than being clamped into a feasible window.
13. **Can later departure create new decisions?** Not in this revision: the fixed nominal decision horizon has no new variables for later slots.
14. **What is requested energy?** It is an input requirement, distinct from energy actually delivered. The measured delivery residual is not proof of a change in true demand.
15. **Why use an Ising Hamiltonian?** Substituting `x_i=(1-Z_i)/2` represents the same binary objective with diagonal qubit operators.
16. **What is the cost Hamiltonian?** `H_C=Σh_i Z_i+ΣJ_ij Z_i Z_j+offset`, encoding the QUBO energy in computational-basis states.
17. **What is superposition?** Hadamard gates prepare amplitudes over many computational-basis bitstrings; measurement returns one bitstring per shot.
18. **What does cost evolution do?** `exp(-iγH_C)` applies energy-dependent phases. The identity offset produces only a global phase.
19. **What does the mixer do?** `exp(-iβΣX)` rotates each qubit around X, allowing amplitudes of different assignments to interfere.
20. **What does p mean?** It is the number of cost/mixer layers. More layers increase circuit resources and do not guarantee better outcomes for a limited optimizer budget.
21. **What does COBYLA optimize?** It adjusts the QAOA angles based on sampled circuit energy; it does not enumerate or directly solve the scheduling problem.
22. **What is a shot?** One circuit execution and measurement. The pilot uses 256 shots for each sampled expectation or final sampling operation.
23. **How is a bitstring decoded?** Qiskit displays qubit zero at the right; `run_qaoa` reverses the displayed string to recover variable order. The final two variables in this pilot are slack.
24. **Feasibility versus optimality?** Feasibility concerns physical constraints; optimality compares objective values. A feasible state can be suboptimal, including because of its slack bits.
25. **How is the classical reference obtained?** The pilot evaluates all 64 binary states and takes the smallest QUBO energy.
26. **How were empirical scenarios generated?** The corrected real-data experiment is not yet integrated. The historical implementation clusters observed departure and delivery residuals, but its interpretation and weighting need correction.
27. **What is data leakage?** Using held-out outcomes to fit or tune a scheduling method. Revised claims must acknowledge the earlier held-out outcomes were already inspected.
28. **What is an oracle?** A benchmark with access to realized future information, separately optimized for each case. The historical F3 implementation does not meet that standard and must not be trusted.
29. **Why might scenario scheduling perform worse?** Scenario distribution mismatch, penalty choices, or sacrificing nominal performance can hurt; the historical comparison cannot establish the cause because its evaluator is defective.
30. **Simulator versus quantum hardware?** Aer executes a classical simulation; it does not measure hardware noise, quantum speedup or hardware reliability.
31. **How are confidence intervals interpreted?** The revised helper resamples paired eligible sessions and adjusts alpha for the declared number of comparisons; independence is an assumption, and clustered sensitivity is still needed.
32. **What is the main limitation?** The corrected ACN experiment, integrated capacity model, oracle, statistical analysis and complete validation are unfinished. The current pilot supports only small synthetic conclusions.

The numerical example and implementation references are in `MATHEMATICAL_WALKTHROUGH.md` and `CODE_TO_THEORY_MAP.md`. These answers describe the current work, not a completed research paper.
