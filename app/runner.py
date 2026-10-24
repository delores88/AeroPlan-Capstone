"""Versioned policy dispatch; historical configurations retain their semantics."""

POLICY_MODES = [
    {"value": "cost_service", "label": "Cost and service"},
    {"value": "research", "label": "Forecast accuracy"},
]


def check_new_run(raw):
    if not isinstance(raw, dict):
        raise ValueError("Study settings must be an object.")
    settings = dict(raw)
    mode = settings.pop("policy_mode", "cost_service")
    if mode == "research":
        from .study import config_checked
        return config_checked(settings)
    if mode == "cost_service":
        from .optimization import config_checked
        return config_checked({**settings, "policy_mode": mode})
    raise ValueError("Unknown inventory policy mode.")


def run_configured(dataset, config, *args, **kwargs):
    # Records predating policy_mode always use their original algorithm.
    mode = config.get("policy_mode", "research")
    if mode == "research":
        from .study import run_study
        return run_study(dataset, {k: v for k, v in config.items() if k != "policy_mode"}, *args, **kwargs)
    if mode == "cost_service":
        from .optimization import run_optimized_study
        return run_optimized_study(dataset, config, *args, **kwargs)
    raise ValueError("Unknown inventory policy mode.")
