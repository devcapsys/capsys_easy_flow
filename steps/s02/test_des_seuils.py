# -*- coding: utf-8 -*-

import time, sys, os
if __name__ == "__main__":
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
import configuration  # Custom
from modules.capsys_mysql_command.capsys_mysql_command import (GenericDatabaseManager, DatabaseConfig) # Custom

def get_info():
    return "Cette étape teste les seuils de fonctionnement du radar."

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

    # Paramètres spécifiques seuils
    min = config.configItems.test_seuils.min_map
    max = config.configItems.test_seuils.max_map
    cmd = "test seuil 50 100 150\r"
    expected_prefix = "--> ok : "
    replace_map = [("--> ok : ", ""), ("- ", "")]
    save_prefix = "TEST_SEUILS_"
    units_map = ["dB", "dB", "dB"]
    timeout = 2

    # Retry logic for the command
    for attempt in range(1, config.max_retries + 1):
        log(f"Exécution de l'étape test des seuils (tentative {attempt}/{config.max_retries})", "yellow")

        status, msg = config.run_meas_on_patch(
            log, step_name_id, min, max, cmd, expected_prefix, save_prefix, units_map, timeout, replace_map
        )
        if status != 0:
            if attempt < config.max_retries:
                log(f"Réessaie de \"{cmd}\"... (tentative {attempt + 1}/{config.max_retries})", "yellow")
                time.sleep(1)
                continue
            else:
                if isinstance(msg, list):
                    for item in msg:
                        return_msg["infos"].append(f"{item}")
                else:
                    return_msg["infos"].append(f"{msg}")
                return status, return_msg
        else:
            return_msg["infos"].append(f"OK")
            return 0, return_msg
    return_msg["infos"].append(f"NOK")
    return 1, return_msg


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