# -*- coding: utf-8 -*-

import time, sys, os
if __name__ == "__main__":
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
import configuration  # Custom
from modules.capsys_mysql_command.capsys_mysql_command import (GenericDatabaseManager, DatabaseConfig) # Custom

def get_info():
    return "Cette étape mesure la consommation du patch."

def run_step(log, config: configuration.AppConfig):
    step_name = os.path.splitext(os.path.basename(__file__))[0]
    return_msg = {"step_name": step_name, "infos": []}
    # Ensure db is initialized
    if not hasattr(config, "db") or config.db is None:
        return_msg["infos"].append(f"config.db n'est pas initialisé.")
        return 1, return_msg
    # We always save the name of the step in the db
    step_name_id = config.db.create(
        "step_name", {
            "device_under_test_id": config.device_under_test_id,
            "step_name": os.path.splitext(os.path.basename(__file__))[0],
        }
    )

    if config.multimeter_current is None:
        return_msg["infos"].append(f"{step_name} : le multimètre de courant n'est pas initialisé.")
        return 1, return_msg
    
    # Verify current limits
    current_min = config.configItems.consumption.minimum
    current_max = config.configItems.consumption.maximum
    name = config.configItems.consumption.key
    unit = "A"
    current = float(config.multimeter_current.meas())
    log(f"Courant mesuré : {current}{unit}, min={current_min}{unit}, max={current_max}{unit}", "blue")
    id = config.save_value(step_name_id, name, current, unit, min_value=current_min, max_value=current_max)
    if current > float(current_max) or current < float(current_min):
        return_msg["infos"].append(f"Courant mesuré {current}{unit} hors des limites ({current_min}{unit} - {current_max}{unit}).")
        return 1, return_msg
    config.db.update_by_id("skvp_float", id, {"valid": 1})

    return_msg["infos"].append(f"OK")
    return 0, return_msg


if __name__ == "__main__":
    """Allow to run this script directly for testing purposes."""

    def log_message(message, color):
        print(f"{color}: {message}")

    # Initialize config
    config = configuration.AppConfig()
    config.arg.show_all_logs = False

    # Initialize Database
    config.db_config = DatabaseConfig(password="root")
    config.db = GenericDatabaseManager(config.db_config, debug=False)
    config.db.connect()
    
    # Launch the initialisation step
    from steps.s01.initialisation import run_step as run_step_init
    success_end, message_end = run_step_init(log_message, config)
    print(message_end)
    
    # Launch this step
    success, message = run_step(log_message, config)
    print(message)

    # Clear ressources
    from steps.zz.fin_du_test import run_step as run_step_fin_du_test
    success_end, message_end = run_step_fin_du_test(log_message, config)
    print(message_end)