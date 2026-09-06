"""Engine implementations.

Each module registers one or more Engines in the registry. Engines follow the
trust doctrine from the 41-project survey: structured LLM output validated by
schemas, deterministic rules computed locally (never trusted to the model),
and evidence carried on every claim.
"""
