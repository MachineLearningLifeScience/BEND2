"""BEND 2.0: benchmark the capabilities needed to design DNA."""

from bend2.catalog import tasks
from bend2.model import Model

__version__ = "0.2.0.dev0"
__all__ = ["Model", "Run", "evaluate", "tasks"]


def evaluate(
    model, *, tasks="atlas_profile", output=None, batch_size=32, cache_dir=None, progress=None
):
    """Evaluate a model; see :func:`bend2.runner.evaluate` for the complete contract."""
    from bend2.runner import evaluate as run

    return run(
        model,
        tasks=tasks,
        output=output,
        batch_size=batch_size,
        cache_dir=cache_dir,
        progress=progress,
    )


def __getattr__(name):
    if name == "Run":
        from bend2.results import Run

        return Run
    raise AttributeError(name)
