# import importlib
# import sys
# import warnings
#
# #map old module paths -> new module paths
# _ALIASES = {
#     "scripts.monitor_system": "scripts.monitor.monitor_system",
#     "scripts.network_tools": "scripts.monitor.network_tools",
#     "scripts.process_monitor": "scripts.monitor.process_monitor",
#     "scripts.service_monitor": "scripts.monitor.service_monitor",
#     "scripts.recovery_tool": "scripts.monitor.recovery_tool",
#     "db_logger": "db.db_logger",
# }
#
# def _install_alias(old_name: str, new_name: str):
#     """Make 'import old_name' load new_name, and expose as attribute on parent package."""
#     try:
#         target = importlib.import_module(new_name)
#         # 1) Make the old fully-qualified module point to the new one
#         sys.modules[old_name] = target
#
#         # 2) Expose as attribute on its parent package (so `from scripts import monitor_system` works)
#         pkg_name, _, submod = old_name.rpartition(".")
#         if pkg_name and pkg_name in sys.modules:
#             setattr(sys.modules[pkg_name], submod, target)
#
#         # 3) Optional: deprecation warning once per import
#         warnings.warn(
#             f"DEPRECATION: '{old_name}' has moved to '{new_name}'. "
#             f"Please update your imports.",
#             DeprecationWarning,
#             stacklevel=2,
#         )
#     except Exception as e:
#         warnings.warn(f"Failed alias {old_name} -> {new_name}: {e}", RuntimeWarning)
#
# for old_mod, new_mod in _ALIASES.items():
#     _install_alias(old_mod, new_mod)