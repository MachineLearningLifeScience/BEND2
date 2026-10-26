"""BEND 2.0: a benchmark for DNA models."""

from bend2.catalog import tasks
from bend2.model import Model

__version__ = "0.2.0.dev0"
__all__ = ["Model", "Run", "evaluate", "plan", "combine", "tasks"]


def evaluate(
    model, *, tasks="atlas_profile", output=None, batch_size=32, cache_dir=None, progress=None
):
    """Evaluate a model; see :func:`bend2.runner.evaluate` for parameters."""
    from bend2.runner import evaluate as run

    return run(
        model,
        tasks=tasks,
        output=output,
        batch_size=batch_size,
        cache_dir=cache_dir,
        progress=progress,
    )


def combine(runs, output):
    """Combine task results from one model into a new run directory."""
    from bend2._combine import combine as merge

    return merge(runs, output)


def __getattr__(name):
    if name == "Run":
        from bend2.results import Run

        return Run
    if name == "plan":
        from bend2.planning import plan

        return plan
    raise AttributeError(name)
