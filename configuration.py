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
                )
            )

    class ConfigItem:
        """Represents a single configuration item loaded from config.json or database."""
        def __init__(
            self,
            key = "",
            port = "",
        ):
            """Initialize a ConfigItem with optional parameters for test configuration."""
            self.key = key
            self.port = port
    
    def __init__(self):
        """Initialize all ConfigItem attributes for different test parameters."""
        self.multimeter_current = self.ConfigItem()
        self.alim = self.ConfigItem()
        self.serial_patch_easy_flow = self.ConfigItem()
        self.serial_target_capsys = self.ConfigItem()

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