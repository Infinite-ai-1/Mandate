"""Locate shared contract models; never substitute production fallback models."""
import importlib

def shared_model(name):
    for module_name in ("schemas", "mandate.schemas"):
        try:
            module=importlib.import_module(module_name)
        except ModuleNotFoundError as error:
            if error.name not in (module_name, module_name.split('.')[0]):
                raise
            continue
        if hasattr(module,name):
            return getattr(module,name)
    raise ImportError(
        f"Shared {name} model is unavailable. AGENTS.md requires it, but the "
        "current mandate.schemas defines a different contract. The shared owner "
        "must reconcile these models before production integration."
    )
