# Scanner Production Baselines

This directory stores immutable Scanner production baseline manifests used by Simulation.

A manifest identifies the exact Scanner production source state and policy contract used by a Simulation run. Existing manifests must not be edited or overwritten. When Production Scanner behavior changes, increment the Scanner version, pass regression tests, and freeze a new manifest.

Research-only rules such as B.2.6 Overextension and the rejected B.2.7 Volume-Low Guard are not part of the production baseline.
