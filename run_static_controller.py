
from os_ken.base import app_manager
from os_ken.lib import hub

app_mgr = app_manager.AppManager.get_instance()
app_mgr.load_apps(["static_controller"])
contexts = app_mgr.create_contexts()
services = app_mgr.instantiate_apps(**contexts)
hub.joinall(services)
