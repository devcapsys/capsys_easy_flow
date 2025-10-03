import os
from typing import Optional
import atexit
from modules.capsys_mysql_command.capsys_mysql_command import (GenericDatabaseManager, DatabaseConfig) # Custom
from modules.capsys_serial_instrument_manager.capsys_serial_instrument_manager import SerialInstrumentManager  # Custom
from modules.capsys_wrapper_tm_t20iii.capsys_wrapper_tm_t20III import PrinterDC  # Custom
from modules.capsys_serial_instrument_manager.rsd3305p import alimentation_rsd3305p  # Custom
from modules.capsys_serial_instrument_manager.mp730424.multimeter_mp730424 import Mp730424Manager  # Custom

# Initialize global variables
CURRENTH_PATH = os.path.dirname(__file__)
NAME_GUI = "Template"
CONFIG_JSON_NAME = "config_template"
VERSION = "V1.0.0"
HASH_GIT = "DEBUG" # Will be replaced by the Git hash when compiled with command .\build.bat
AUTHOR = "Thomas GERARDIN"
PRINTER_NAME = "EPSON TM-T20III Receipt"

def get_project_path(*paths):
    """Return the absolute path from the project root, regardless of current working directory."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), *paths))

class SerialPatchEasyFlow(SerialInstrumentManager):
    def __init__(self, port=None, baudrate=115200, timeout=0.3, debug=False):
        SerialInstrumentManager.__init__(self, port, baudrate, timeout, debug)
        self._debug_log("PatchManager initialized")

    def get_valid(self, sn=None) -> bool:
        idn = self.send_command("help\r", timeout=1) # Example : help = "Command disp : prod param stat all"
        if not idn:
            raise RuntimeError("Failed to get valid IDN response")
        if idn.startswith("Command disp :\r prod\r param\r"):
            self._debug_log(f"Device IDN: {idn}")
            return True
        else:
            raise RuntimeError(f"Invalid device IDN: {idn}")
        
class SerialTargetCapsys(SerialInstrumentManager):
    def __init__(self, port=None, baudrate=921600, timeout=0.3, debug=False):
        SerialInstrumentManager.__init__(self, port, baudrate, timeout, debug)
        self._debug_log("TargetCapsys initialized")

    def get_valid(self, sn=None) -> bool:
        self.send_command("\r", timeout=1)
        idn = self.send_command("help\r", timeout=1) # Example : help = "Command disp : prod param stat all"
        if not idn:
            raise RuntimeError("Failed to get valid IDN response")
        if idn.startswith("Command disp :\r param\r all\r\r"):
            self._debug_log(f"Device IDN: {idn}")
            return True
        else:
            raise RuntimeError(f"Invalid device IDN: {idn}")
        
class ConfigItems:
    """Container for all configuration items used in the test sequence."""
    key_map = {
        "MULTIMETRE_COURANT": "multimeter_current",
        "ALIMENTATION": "alim",
        "PATCH": "serial_patch_easy_flow",
        "TARGET_CAPSYS": "serial_target_capsys",
        "TEST_SEUILS": "test_seuils",
        "TEST_BF": "bf",
        "MESURE_CONSOMMATION_PATCH": "consumption",
    }

    def init_config_items(self, configJson):
        """Initialize configItems attributes from the config JSON mapping pins and keys."""
        key_map = ConfigItems.key_map
        # For each element of config.json, create a corresponding ConfigItem
        for json_key, attr_name in key_map.items():
            item = configJson.get(json_key, {}) # Retrieves the JSON object or {} if absent
            # Create the ConfigItem with all the parameters from the JSON
            setattr(
                self,
                attr_name,
                ConfigItems.ConfigItem(                
                    key=json_key,
                    port=item.get("port"),
                    min_map=item.get("min_map"),
                    max_map=item.get("max_map"),
                    minimum=item.get("minimum"),
                    maximum=item.get("maximum"),
                )
            )

    class ConfigItem:
        """Represents a single configuration item loaded from config.json or database."""
        def __init__(
            self,
            key = "",
            port = "",
            min_map = None,
            max_map = None,
            minimum = None,
            maximum = None,
        ):
            """Initialize a ConfigItem with optional parameters for test configuration."""
            self.key = key
            self.port = port
            self.min_map = min_map
            self.max_map = max_map
            self.minimum = minimum
            self.maximum = maximum

    def __init__(self):
        """Initialize all ConfigItem attributes for different test parameters."""
        self.multimeter_current = self.ConfigItem()
        self.alim = self.ConfigItem()
        self.serial_patch_easy_flow = self.ConfigItem()
        self.serial_target_capsys = self.ConfigItem()
        self.test_seuils = self.ConfigItem()
        self.bf = self.ConfigItem()
        self.consumption = self.ConfigItem()

class Arg:
    name = NAME_GUI
    version = VERSION
    hash_git = HASH_GIT
    author = AUTHOR
    show_all_logs = False
    operator = AUTHOR
    commande = ""
    of = ""
    article = ""
    indice = ""
    product_list_id = "1"
    user = "root"
    password = "root"
    host = "127.0.0.1"
    port = "3306"
    database = "capsys_db_bdt"
    product_list: Optional[dict] = None
    parameters_group: list[str] = []
    external_devices: Optional[list[str]] = None
    script: Optional[str] = None

class AppConfig:
    def __init__(self):
        self.arg = Arg()
        self.db_config: Optional[DatabaseConfig] = None
        self.db: Optional[GenericDatabaseManager] = None
        self.device_under_test_id: Optional[int] = None
        self.configItems = ConfigItems()
        self.printer: Optional[PrinterDC] = None
        self.max_retries = 2
        self.multimeter_current: Optional[Mp730424Manager] = None
        self.alim: Optional[alimentation_rsd3305p.Rsd3305PManager] = None
        self.serial_patch_easy_flow: Optional[SerialPatchEasyFlow] = None
        self.serial_target_capsys: Optional[SerialTargetCapsys] = None
        atexit.register(self.cleanup) # Register cleanup function to be called on exit

    def cleanup(self):
        if self.db:
            self.db.disconnect()
            self.db = None
        if self.serial_target_capsys:
            self.serial_target_capsys.close()
            self.serial_target_capsys = None
        if self.multimeter_current:
            self.multimeter_current.close()
            self.multimeter_current = None
        if self.serial_patch_easy_flow:
            self.serial_patch_easy_flow.close()
            self.serial_patch_easy_flow = None
        if self.alim:
            self.alim.set_output(1, False)
            self.alim.set_output(2, False)
            self.alim.close()
            self.alim = None
        self.device_under_test_id = None
        
    def save_value(self, step_name_id: int, key: str, value: float, unit: str = "", min_value: Optional[float] = None, max_value: Optional[float] = None, valid: int = 0):
        """Save a key-value pair in the database."""
        if not self.db or not self.device_under_test_id:
            raise ValueError("Database or device under test ID is not initialized.")
        id = self.db.create("skvp_float",
                       {"step_name_id": step_name_id, "key": key, "val_float": value, "unit": unit, "min_configured": min_value, "max_configured": max_value, "valid": valid})
        return id
    
    def run_meas_on_patch(
        self,
        log,
        step_name_id,
        min_values,
        max_values,
        command_to_send,
        expected_prefix,
        save_key_prefix = "",  # type: str | list | dict
        seuil_unit_map = {},    # type: str | list | dict
        timeout=4,
        replace_map={},
        fct=None
    ):
        return_msg_fail = []
        if self.serial_patch_fmcw is None:
            return 1, "Erreur : le patch n'est pas initialisé."
        if self.arg.product_list is None:
            return 1, "Erreur : la liste de production n'est pas initialisée."
        log(f"Envoi de la commande : \"{command_to_send}\"", "blue")
        response = self.serial_patch_fmcw.send_command(command_to_send, timeout=timeout)
        log(f"Réponse du patch : {response}", "blue")
        response = fct(response) if fct else response
        if not response.startswith(expected_prefix):
            self.serial_patch_fmcw.close()
            self.serial_patch_fmcw = None
            return 1, f"Réponse inattendue du patch \"{command_to_send}\". Le port est fermé."
        # Appliquer les remplacements
        if isinstance(replace_map, dict):
            for k, v in replace_map.items():
                response = response.replace(k, v)
        elif isinstance(replace_map, list):
            for k, v in replace_map:
                response = response.replace(k, v)
        response = response.strip()
        values = []
        valid = 1
        expected_values_count = len(min_values)
        for i, val in enumerate(response.split(" ")):
            if val.strip():
                try:
                    val_float = float(val.strip())
                except ValueError:
                    log(f"{i+1} : valeur non numérique '{val.strip()}'", "red")
                    return_msg_fail.append(f"{i+1} : valeur non numérique '{val.strip()}'")
                    valid = 0
                    break
                if i < expected_values_count:
                    if min_values[i] <= val_float <= max_values[i]:
                        log(f"{i+1} : {val_float} (OK ; min={min_values[i]} ; max={max_values[i]})", "blue")
                        values.append(val_float)
                    else:
                        log(f"{i+1} : {val_float} (NOK ; min={min_values[i]} ; max={max_values[i]})", "red")
                        values.append(val_float)
                        return_msg_fail.append(f"{i+1} : {val_float} (NOK ; min={min_values[i]} ; max={max_values[i]})")
                        valid = 0
        
        # Save all valid values, even on error
        if save_key_prefix != "":
            for i, val_float in enumerate(values):
                # If save_key_prefix is a dict/map, use mapping
                if isinstance(save_key_prefix, dict):
                    key = save_key_prefix.get(i, f"val{i+1}")
                # If save_key_prefix is a list, use index
                elif isinstance(save_key_prefix, list) and i < len(save_key_prefix):
                    key = save_key_prefix[i]
                # If save_key_prefix is a string, use as prefix
                elif isinstance(save_key_prefix, str):
                    key = f"{save_key_prefix}{i+1}"
                else:
                    key = f"val{i+1}"
                unit = seuil_unit_map[i] if isinstance(seuil_unit_map, list) and i < len(seuil_unit_map) else (seuil_unit_map.get(i, "") if isinstance(seuil_unit_map, dict) else "")
                self.save_value(step_name_id, key, val_float, unit, min_value=min_values[i], max_value=max_values[i], valid=valid)

        if valid:
            return 0, "Mesure réussie."
        else:
            return 1, return_msg_fail