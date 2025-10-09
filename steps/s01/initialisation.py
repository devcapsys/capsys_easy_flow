# -*- coding: utf-8 -*-
import sys
import os
if __name__ == "__main__":
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
from datetime import datetime
import json, time
import configuration  # Custom
from modules.capsys_mysql_command.capsys_mysql_command import (GenericDatabaseManager, DatabaseConfig, Operator) # Custom
from modules.capsys_serial_instrument_manager.mp730424.multimeter_mp730424 import Mp730424Manager  # Custom
from modules.capsys_serial_instrument_manager.rsd3305p import alimentation_rsd3305p  # Custom
from configuration import VERSION, get_project_path

def get_info():
    return "Cette étape crée device_under_test, initialise le DAQ, l'alimentation et le MCP23017."    

def init_database_and_checks(log, config: configuration.AppConfig):
    # Ensure db is initialized
    if not hasattr(config, "db") or config.db is None:
        return 1, "config.db n'est pas initialisé."
    # Checks that all attributes of config.arg are not empty
    for field, value in vars(config.arg).items():
        if value is None:
            return 1, f"Pas de valeur sur {field}"

    # Check operator format
    if not isinstance(config.arg.operator, str) or len(config.arg.operator.split()) < 2:
        return (1, "Le champ 'operator' doit contenir au moins un prénom et un nom.")

    # Retrieve operator from database
    operators = config.db.get_by_column("operator", "name", config.arg.operator.split()[1])
    if not operators:
        return 1, f"Aucun opérateur {config.arg.operator.split()[1]} trouvé dans la base de données."
    operator = Operator(**operators[0])
    operator_id = operator.id

    # Retrieve product_list from database
    config.arg.product_list = config.db.get_by_id("product_list", config.arg.product_list_id)
    if not config.arg.product_list:
        return 1, "Aucun produit trouvé dans la base de données."

    # Retrieve bench_composition from database
    bench_composition_id = config.arg.product_list.get("bench_composition_id")
    bench_composition_raw = config.db.get_by_column("bench_composition", "id", bench_composition_id)
    bench_composition = bench_composition_raw if bench_composition_raw else []
    if not bench_composition:
        return (1, "Problème lors de la récupération de la composition du banc dans la base de données.")

    # Retrieve all externals devices from database
    external_devices = []
    for external_device in bench_composition:
        external_device_data = config.db.get_by_id("external_device", external_device["external_device_id"])
        if external_device_data:
            external_devices.append(external_device_data)
    if not external_devices:
        return (1, "Problème lors de la récupération des périphériques externes dans la base de données.")

    # Retrieve script from database
    script_data = config.db.get_by_id("script", config.arg.product_list_id)
    if not script_data:
        return (1, "Problème lors de la récupération du script dans la base de données.")
    # Remove the "file" key if it exists because it's too large to store in the database
    if "file" in script_data:
        del script_data["file"]
    script = script_data

    # Retrieve parameters_group from database
    parameters_group_id = config.arg.product_list.get("parameters_group_id")
    parameters_group_raw = config.db.get_by_column("parameters_group", "parameters_group_id", parameters_group_id)
    parameters_group = parameters_group_raw if parameters_group_raw else []
    if not parameters_group:
        return (1, "Problème lors de la récupération des groupes de paramètres dans la base de données.")

    # Retrieve all parameters from database
    parameters = []
    for group in parameters_group:
        parameters_data = config.db.get_by_id("parameters", group["parameters_id"])
        if parameters_data:
            parameters.append(parameters_data)
    if not parameters:
        return (1, "Problème lors de la récupération des paramètres dans la base de données.")

    # Retrieve and save config.json from database
    # config.json is used to store values used during the test
    data_str = None
    txt = ""
    for parameter in parameters:
        config_json_name = configuration.CONFIG_JSON_NAME
        if parameter.get("name") == config_json_name:
            data_str = parameter.get("file")
            txt = f"Le fichier de config utilisé correspond à la ligne id={parameter.get('id')} de la table parameters"
            log(txt, "blue")
    if data_str == None:
        return (1, "Le fichier config n'est pas présent dans la ddb.")
    
    # Write and read config.json file with proper exception handling
    config_path = get_project_path("config.json")
    configJson = {}
    try:
        # Write the config file
        with open(config_path, "wb") as f:
            f.write(data_str)
        
        # Read the config file immediately after writing
        with open(config_path, 'r', encoding='utf-8') as json_file:
            configJson = json.load(json_file)
    except Exception as e:
        # Clean up the file if it was created but reading failed
        try:
            if os.path.exists(config_path):
                os.remove(config_path)
        except Exception as cleanup_error:
            log(f"Problème lors du nettoyage du fichier config : {cleanup_error}", "yellow")
        return 1, f"Problème lors de la création/lecture de config.json : {e}"

    # Initialize configItems attributes from the config JSON mapping pins and keys from config.json in ddb
    config.configItems.init_config_items(configJson)

    # Create device_under_test
    device_under_test_data = {
        "operator_id": operator_id,
        "product_id": config.arg.product_list_id,
        "sn": config.arg.article,
        "date": datetime.now(),
        "result": 0,
        "of": config.arg.of,
        "command_number": config.arg.commande,
        "client": "",
        "failure_label": "",
        "name": config.arg.name
    }
    config.device_under_test_id = config.db.create("device_under_test", device_under_test_data)

    log(f"Device Under Test créé avec l'ID {config.device_under_test_id}.", "purple")

    step_name_id = config.db.create("step_name",
        {"device_under_test_id": config.device_under_test_id, "step_name": os.path.splitext(os.path.basename(__file__))[0]}
    )

    # Create the data dictionary to be inserted into skvp_json
    data = {
        "device_under_test_id": config.device_under_test_id,
        "operator": operator.to_dict() if hasattr(operator, 'to_dict') else vars(operator),
        "product_list": config.arg.product_list,  # already a dictionary
        "bench_composition": bench_composition,  # already a list of dictionaries
        "external_devices": external_devices,   # already a list of dictionaries
        "script": script,                       # already a dictionary
        "parameters_group": parameters_group,   # already a list of dictionaries
        "parameters": parameters,               # already a list of dictionaries
    }

    config.save_value(step_name_id, "VERSION", VERSION)
    config.save_value(step_name_id, "data_used_for_test", json.dumps(data, indent=4, ensure_ascii=False, default=str))
    config.save_value(step_name_id, "id_fichier_config", txt)

    return 0, step_name_id

def init_multimeter_current(log, config: configuration.AppConfig):
    config.multimeter_current = None
    log("Initialisation du multimètre en courant...", "cyan")
    multimeter = Mp730424Manager(debug=config.arg.show_all_logs)
    if configuration.HASH_GIT == "DEBUG":
        log("En mode DEBUG, il faut bien penser à changer le port.", "cyan")
        port = "COM19" # PC TGE
    else:
        port = config.configItems.multimeter_current.port
    try:
        if multimeter.open_with_usb_name_and_sn(usb_name="USB Serial Port", sn="24140430", start_with_port=port):
            log(multimeter.identification(), "blue")
            multimeter.reset()
            multimeter.conf_curr_dc()
            multimeter.send_command("RANGE:ACI 4\n")
            multimeter.send_command("RATE F\n")
        else:
            return 1, "Impossible de se connecter au multimètre MP730424."
    except Exception as e:
        return 1, f"Problème lors de l'initialisation du multimètre : {e}"
    # At this point, multimeter_current is good so we put it in the global config
    config.multimeter_current = multimeter
    return 0, "Multimètre initialisé avec succès."

def init_alimentation(log, config: configuration.AppConfig):
    config.alim = None
    log("Initialisation de l'alimentation...", "cyan")
    alim = alimentation_rsd3305p.Rsd3305PManager(debug=config.arg.show_all_logs)
    if configuration.HASH_GIT == "DEBUG":
        log("En mode DEBUG, il faut bien penser à changer le port.", "cyan")
        port = "COM20" # PC TGE
    else:
        port = config.configItems.alim.port
    try:
        if alim.open_with_usb_name_and_sn("Périphérique série USB", "29599382", start_with_port=port):
            log(f"{alim.identification()}", "blue")
            alim.set_output(1, False)
            alim.set_output(2, False)
            alim.set_tracking_mode(0)
            alim.set_voltage(2, 12.00)
            alim.set_current(2, 0.5)
            alim.set_output(2, True)
        else:
            return 1, "Impossible de se connecter à l'alimentation RSD3305P."
    except Exception as e:
        return 1, f"Problème lors de l'initialisation de l'alimentation : {e}"
    # At this point, alim is good so we put it in the global config
    config.alim = alim
    return 0, "Alimentation initialisée avec succès."

def init_patch_easy_flow(log, config: configuration.AppConfig):
    config.serial_patch_easy_flow = None
    log("Initialisation du patch easy flow...", "cyan")
    # Ensure that the alim is initialized
    if config.alim == None:
        return 1, "L'alimentation n'est pas initialisée ou connectée."
    try:
        config.serial_patch_easy_flow = configuration.SerialPatchEasyFlow()
        if configuration.HASH_GIT == "DEBUG":
            log("En mode DEBUG, il faut bien penser à changer le port.", "cyan")
            port = "COM28" # PC TGE
        else:
            port = config.configItems.serial_patch_easy_flow.port
        config.serial_patch_easy_flow.open_with_port(port)
        log(f"Patch easy flow ouvert sur : {config.serial_patch_easy_flow.port}", "blue")
    except Exception as e:
        return 1, f"Problème lors de l'initialisation du patch easy flow : {e}"
    return 0, "Patch easy flow initialisée avec succès."

def init_target_capsys(log, config: configuration.AppConfig):
    config.serial_target_capsys = None
    log("Initialisation de la target Capsys...", "cyan")
    config.serial_target_capsys = configuration.SerialTargetCapsys()
    if configuration.HASH_GIT == "DEBUG":
        log("En mode DEBUG, il faut bien penser à changer le port.", "cyan")
        port = "COM23" # PC TGE
    else:
        port = config.configItems.serial_target_capsys.port
    config.serial_target_capsys.open_with_port(port)
    log(f"Target Capsys ouvert sur : {config.serial_target_capsys.port}", "blue")
    config.serial_target_capsys.send_command("set emetteur off\r", expected_response="ok", timeout=2)
    return 0, "Target Capsys initialisée avec succès."

def run_step(log, config: configuration.AppConfig):
    all_ok = 1
    step_name = os.path.splitext(os.path.basename(__file__))[0]
    return_msg = {"step_name": step_name, "infos": []}
    log(f"show_all_logs = {config.arg.show_all_logs}", "blue")
    status, step_name_id = init_database_and_checks(log, config)
    if status != 0:
        return_msg["infos"].append(f"{step_name_id}")
        return status, return_msg

    try:
        multimeter_is_open = (config.multimeter_current is not None and getattr(getattr(config.multimeter_current, 'ser', None), 'is_open', False))
    except (AttributeError, TypeError):
        multimeter_is_open = False
    if not multimeter_is_open:
        status, message = -1, "Erreur inconnue lors de l'initialisation du multimètre courant."
        status, message = init_multimeter_current(log, config)
        log(message, "blue")
        if status != 0:
            all_ok = 0
            if config.multimeter_current is not None:
                config.multimeter_current.close()
            config.multimeter_current = None
            return_msg["infos"].append(f"{message}")
            return status, return_msg
    else:
        log("Le multimètre en courant est déjà initialisé.", "blue")

    try:
        alim_is_open = (config.alim is not None and getattr(getattr(config.alim, 'ser', None), 'is_open', False))
    except (AttributeError, TypeError):
        alim_is_open = False
    if not alim_is_open:
        status, message = -1, "Erreur inconnue lors de l'initialisation de l'alimentation."
        status, message = init_alimentation(log, config)
        log(message, "blue")
        if status != 0:
            all_ok = 0
            if config.alim is not None:
                config.alim.close()
            config.alim = None
            return_msg["infos"].append(f"{message}")
            return status, return_msg
    else:
        log("L'alimentation est déjà initialisée.", "blue")

    try:
        target_capsys_is_open = (config.serial_target_capsys is not None and getattr(getattr(config.serial_target_capsys, 'ser', None), 'is_open', False))
    except (AttributeError, TypeError):
        target_capsys_is_open = False
    if not target_capsys_is_open:
        status, message = -1, "Erreur inconnue lors de l'initialisation de la target Capsys."
        status, message = init_target_capsys(log, config)
        log(message, "blue")
        if status != 0:
            all_ok = 0
            if config.serial_target_capsys is not None:
                config.serial_target_capsys.close()
            config.serial_target_capsys = None
            return_msg["infos"].append(f"{message}")
            return status, return_msg

    try:
        patch_is_open = (config.serial_patch_easy_flow is not None and getattr(getattr(config.serial_patch_easy_flow, 'ser', None), 'is_open', False))
    except (AttributeError, TypeError):
        patch_is_open = False
    if not patch_is_open:
        status, message = init_patch_easy_flow(log, config)
        log(message, "blue")
        if status != 0:
            all_ok = 0
            if config.serial_patch_easy_flow is not None:
                config.serial_patch_easy_flow.close()
            config.serial_patch_easy_flow = None
            return_msg["infos"].append(f"{message}")
            return status, return_msg
    else:
        log("Le patch est déjà initialisé.", "blue")

    if all_ok == 0:
        config.multimeter_current = None
        config.alim = None
        config.serial_patch_easy_flow = None
        config.serial_target_capsys = None
        return_msg["infos"].append("Erreur lors de l'initialisation des instruments.")
        return 1, return_msg
    
    return_msg["infos"].append(f"OK")
    return 0, return_msg

if __name__ == "__main__":
    def log_message(message, color):
        print(f"{color}: {message}")

    # Initialize config
    config = configuration.AppConfig()
    config.arg.show_all_logs = False
    
    # Initialize Database
    config.db_config = DatabaseConfig(password="root")
    config.db = GenericDatabaseManager(config.db_config, debug=False)
    config.db.connect()
    
    success_init, message_init = run_step(log_message, config)
    print(message_init)
    
    # Clear ressources
    from steps.zz.fin_du_test import run_step as run_step_fin_du_test
    success_end, message_end = run_step_fin_du_test(log_message, config)
    print(message_end)


