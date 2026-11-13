"""Publishing is disabled in the anonymous review edition."""


def publish_submission(
    run,
    evidence_repository=None,
    *,
    model_url=None,
    adapter_url=None,
    family="",
    parameter_label="",
    progress=None,
):
    """Reject publication before reading credentials or contacting a service."""
    raise ValueError(
        "GitHub publishing is disabled in the anonymous review edition. "
        "Use draft export and draft submit --evidence-url to prepare local review files."
    )
