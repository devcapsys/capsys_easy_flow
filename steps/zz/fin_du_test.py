# -*- coding: utf-8 -*-
import os
import sys
if __name__ == "__main__":
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
import configuration  # Custom
from modules.capsys_mysql_command.capsys_mysql_command import (GenericDatabaseManager, DatabaseConfig) # Custom
from configuration import get_project_path

def get_info():
    return "Cette étape effectue le nettoyage et la fermeture des ressources en fin de test."

def run_step(log, config: configuration.AppConfig):
    step_name = os.path.splitext(os.path.basename(__file__))[0]
    return_msg = {"step_name": step_name, "infos": []}
    # Ensure db is initialized
    if not hasattr(config, "db") or config.db is None:
        return_msg["infos"].append("Erreur : config.db n'est pas initialisé.")
        return 1, return_msg
    # We always save the name of the step in the db
    config.db.create("step_name", {"device_under_test_id": config.device_under_test_id, "step_name": step_name})
    success = 0

    # delete config.json file
    config_file_path = get_project_path("config.json")
    
    if os.path.exists(config_file_path):
        os.remove(config_file_path)
        log("Fichier config.json supprimé.", "blue")
    else:
        log("Problème lors de la suppression du fichier config.json.", "yellow")
        success = 2

    if success == 0:
        return_msg["infos"].append("Nettoyage effectué avec succès.")
        return success, return_msg
    elif success == 2:
        return_msg["infos"].append("Nettoyage effectué partiellement.")
        return success, return_msg
    else:
        return_msg["infos"].append("Erreur inconnue lors du nettoyage.")
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