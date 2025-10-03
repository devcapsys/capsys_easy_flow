# -*- coding: utf-8 -*-

import time
import sys
import os
if __name__ == "__main__":
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
import configuration  # Custom
from modules.capsys_mysql_command.capsys_mysql_command import (GenericDatabaseManager, DatabaseConfig) # Custom

def get_info():
    return "Cette étape teste TODO."

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
    if config.serial_target_capsys is None:
        return_msg["infos"].append(f"config.serial_target_capsys n'est pas initialisé.")
        return 1, return_msg

    cmd_map_target_capsys = ["set emetteur on\r", "set txmod 225\r", "set freq 450\r", "set freq 810\r"]
    expected_prefix_target_capsys = "--> ok"


    # Paramètres spécifiques seuils
    min_map = config.configItems.bf.min_map
    min_map_sub1 = min_map[0:2]
    min_map_sub2 = min_map[2:4]
    min_map_sub3 = min_map[4:6]
    min_map_groups = [min_map_sub1, min_map_sub2, min_map_sub3]
    max_map = config.configItems.bf.max_map
    max_map_sub1 = max_map[0:2]
    max_map_sub2 = max_map[2:4]
    max_map_sub3 = max_map[4:6]
    max_map_groups = [max_map_sub1, max_map_sub2, max_map_sub3]
    save_prefix_map_sub1 = ["TEST_BF_FREQ_1_Id", "TEST_BF_FREQ_1_AMP_dB"]
    save_prefix_map_sub2 = ["TEST_BF_FREQ_2_Id", "TEST_BF_FREQ_2_AMP_dB"]
    save_prefix_map_sub3 = ["TEST_BF_FREQ_3_Id", "TEST_BF_FREQ_3_AMP_dB"]
    save_prefix_map_groups = [save_prefix_map_sub1, save_prefix_map_sub2, save_prefix_map_sub3]
    cmd = "test bf\r"
    replace_map = [("--> ok : ", ""), ("- ", "")]
    # units_map = config.configItems.bf.units_map
    expected_prefix = "--> ok"
    timeout = 2

    # Retry logic for the command
    for attempt in range(1, config.max_retries + 1):
        all_ok = 1
        log(f"Exécution de l'étape {step_name} (tentative {attempt}/{config.max_retries})", "yellow")

        config.serial_target_capsys.send_command(cmd_map_target_capsys[0], expected_prefix_target_capsys, timeout=3)
        for i in range(3):
            config.serial_target_capsys.send_command(cmd_map_target_capsys[i+1], expected_prefix_target_capsys, timeout=3)
            status, msg = config.run_meas_on_patch(
                log, step_name_id, min_map_groups[i], max_map_groups[i], cmd, expected_prefix, save_prefix_map_groups[i], timeout=timeout, replace_map=replace_map
            )
            if status != 0:
                if attempt < config.max_retries:
                    log(f"Réessaie de \"{cmd}\"... (tentative {attempt + 1}/{config.max_retries})", "yellow")
                    time.sleep(1)
                    break
                else:
                    return_msg["infos"].append(f"{i} : {msg}")
                    return status, return_msg
            else:
                all_ok = 0
        if all_ok == 0:
            return_msg["infos"].append(f"OK")
            log(f"Envoie de la commande \"set emetteur off\" : {config.serial_target_capsys.send_command('set emetteur off\r', expected_response='ok', timeout=2)}", "blue")
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