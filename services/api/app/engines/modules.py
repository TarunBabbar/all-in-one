"""Import engine modules so they self-register into the registry.

Each engine module calls register_engines() at import time. Importing this
package is enough to populate REGISTRY with every consolidated capability.
"""

from __future__ import annotations

from . import (
    a11y,  # noqa: F401
    agent_security,  # noqa: F401
    api_testing,  # noqa: F401
    codegen,  # noqa: F401
    demo,  # noqa: F401
    etl,  # noqa: F401
    eval_gate,  # noqa: F401
    executor,  # noqa: F401
    intake,  # noqa: F401
    leakage,  # noqa: F401
    prompt_eval,  # noqa: F401
    rag,  # noqa: F401
    release_gate,  # noqa: F401
    requirement_doctor,  # noqa: F401
    test_cases,  # noqa: F401
    test_plan,  # noqa: F401
    triage,  # noqa: F401
    visual,  # noqa: F401
)
