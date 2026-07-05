from prometheus_client import REGISTRY

def get_or_create_metric(metric_cls, name, description, labels=None):
    """
    Safely get or create a Prometheus metric to avoid duplicate registration ValueErrors
    when modules are reloaded (e.g. during testing or hot-reloading).
    """
    try:
        return metric_cls(name, description, labels or [])
    except ValueError:
        return REGISTRY._names_to_collectors[name]
