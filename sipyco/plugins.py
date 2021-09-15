import pluggy

import sipyco.hookspecs as hookspecs
import sipyco.pyon as pyon


def get_plugin_manager() -> pluggy.PluginManager:
    """Get the PluginManager for sipyco plugins.

    You can call the plugin hooks via this manager."""
    pm = pluggy.PluginManager("sipyco")
    pm.add_hookspecs(hookspecs)
    pm.register(pyon)
    pm.load_setuptools_entrypoints("sipyco")
    return pm
