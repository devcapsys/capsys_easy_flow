# -*- coding: utf-8 -*-

import sys
import importlib.util
import os
from typing import List, Tuple, Callable
from modules.capsys_mysql_command.capsys_mysql_command import (GenericDatabaseManager, DatabaseConfig) # Custom
from PyQt6.QtGui import QIcon, QCloseEvent
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QMessageBox, QCheckBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from datetime import datetime
import logging, ctypes, tempfile, json
from modules.capsys_pdf_report.capsys_pdf_report import DeviceReport  # Custom
from modules.capsys_wrapper_tm_t20iii.capsys_wrapper_tm_t20III import PrinterDC  # Custom
import configuration  # Custom

# Global config object
config = configuration.AppConfig()

# Call the SetCurrentProcessExplicitAppUserModelID function from shell32.dll
# This sets a unique AppUserModelID for the current process to identify it in the taskbar, start menu, etc.
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("my_unique_app_id")

class TestThread(QThread):
    """Thread to execute test steps in the background, emitting signals for UI updates and handling test logic."""
    update_step = pyqtSignal(int, str, bool, str)
    log_message = pyqtSignal(str, str)
    finished = pyqtSignal()
    step_failed = pyqtSignal(str, str)

    def __init__(self, skipped_steps=None, generate_report=False):
        """Initialize the test thread and load test steps."""
        super().__init__()
        self.running = True
        self.skipped_steps = skipped_steps or set()
        self.steps = self.load_steps()
        self.generate_report = generate_report

    def emit_log_message(self, message, color="white"):
        """Emit a log message signal with the given message and color."""
        # Si le message est un dict, le convertir en chaîne lisible
        if isinstance(message, dict):
            message = json.dumps(message, ensure_ascii=False, indent=2)
        elif isinstance(message, str):
            try:
                # Si le message est une chaîne JSON, le charger puis le retransformer pour formatage
                obj = json.loads(message)
                if isinstance(obj, dict):
                    message = json.dumps(obj, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                pass
        self.log_message.emit(message, color)

    def load_steps(self) -> List[Tuple[str, Callable, Callable]]:
        """Dynamically load test step modules from the 'steps' directory and return a list of (name, run_step, get_info) tuples."""
        steps_folder = os.path.join(os.path.dirname(__file__), "steps")
        # Include the s01, s02, ... folders and the 'zz' folder
        step_dirs = sorted(
            d
            for d in os.listdir(steps_folder)
            if os.path.isdir(os.path.join(steps_folder, d))
            and (d.startswith("s") and d[1:].isdigit() or d == "zz")
        )

        steps = []
        final_step_file = None

        for dir_name in step_dirs:
            dir_path = os.path.join(steps_folder, dir_name)
            py_files = sorted(f for f in os.listdir(dir_path) if f.endswith(".py"))
            for filename in py_files:
                if dir_name == "zz" and filename == "fin_du_test.py":
                    final_step_file = (dir_path, filename)
                    continue
                module_name = f"{dir_name}_{filename[:-3]}"
                filepath = os.path.join(dir_path, filename)
                spec = importlib.util.spec_from_file_location(module_name, filepath)
                module = importlib.util.module_from_spec(spec) # type: ignore[attr-defined]
                spec.loader.exec_module(module)  # type: ignore[attr-defined]
                if hasattr(module, "run_step"):
                    info_func = getattr(module, "get_info", lambda: "Pas d'information disponible pour cette étape.")
                    steps.append((module_name, module.run_step, info_func))

        # Adds Fin du test.py to the end of the test
        if final_step_file:
            dir_path, filename = final_step_file
            module_name = f"{filename[:-3]}"
            filepath = os.path.join(dir_path, filename)
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            module = importlib.util.module_from_spec(spec)  # type: ignore[attr-defined]
            spec.loader.exec_module(module)  # type: ignore[attr-defined]
            if hasattr(module, "run_step"):
                info_func = getattr(module, "get_info", lambda: "Pas d'information disponible pour cette étape.")
                steps.append((module_name, module.run_step, info_func))

        return steps

    def run(self):
        """Main execution loop for running all test steps and handling results, errors, and report generation."""
        self.emit_log_message("=== DÉBUT DU TEST ===", "yellow")
        error_found = False
        failure_message = ""

        for idx, (step_name, step_func, _) in enumerate(self.steps):
            if not self.running:
                error_found = True  # Mark test as NO if interrupted
                break

            # If an error occurs, only the final step is executed
            if error_found and not "fin_du_test" in step_name:
                continue

            # Skip step if it's marked to be skipped
            if idx in self.skipped_steps:
                step_name_str: str = str(step_name)
                self.emit_log_message(f"Étape sautée : {step_name_str.replace('s', '', 1).replace('_', ' ').capitalize()}", "orange")
                self.update_step.emit(idx, "⏭️", 2, "Étape sautée par l'utilisateur")
                continue

            step_name_str: str = str(step_name)
            self.emit_log_message(f"Étape : {step_name_str.replace('s', '', 1).replace('_', ' ').capitalize()}", "cyan")
            self.update_step.emit(idx, "⏳", 2, "Étape en cours")

            try:
                    success, message = step_func(self.emit_log_message, config)
                    if isinstance(message, dict):
                        message = json.dumps(message, ensure_ascii=False, indent=2)
            except (Exception) as e:  # If any bug in steps, we treat them as test passed NOK
                success = 1
                message = f"Exception : {e}"

            if success == 0:  # Test passed OK
                self.emit_log_message(message, "green")
            elif success == 1:  # Test passed NOK
                if config.printer and config.arg.product_list:
                    if config.arg.product_list.get("info") != "debug":
                        try:
                            msg_obj = json.loads(message) if isinstance(message, str) else message
                        except json.JSONDecodeError:
                            msg_obj = message
                        # If dict, extract step_name and pass the rest as infos
                        if isinstance(msg_obj, dict) and "step_name" in msg_obj:
                            label = msg_obj["step_name"]
                            infos = []
                            # If 'infos' exists and is a list, only its elements are displayed
                            if "infos" in msg_obj and isinstance(msg_obj["infos"], list):
                                for v in msg_obj["infos"]:
                                    infos.append({"type": "text", "content": str(v), "align": "l", "weight": 500})
                            else:
                                for k, v in msg_obj.items():
                                    if k != "step_name":
                                        infos.append({"type": "text", "content": f"{k} : {v}", "align": "l", "weight": 500})
                        else:
                            label = str(msg_obj)
                            infos = None
                        config.printer.custom_print_bdt(
                            config.arg.operator,
                            config.arg.product_list.get("info"),
                            config.device_under_test_id,
                            label,
                            infos)
                self.emit_log_message(message, "red")
            else:  # Test passed with WARNING
                self.emit_log_message(message, "yellow")

            # Ensure message is always a string for update_step.emit
            if isinstance(message, dict):
                message_str = json.dumps(message, ensure_ascii=False, indent=2)
            else:
                message_str = str(message)
            self.update_step.emit(idx, "✅" if success == 0 else "❌", success, message_str)

            if success and not step_name.startswith("fin_du_test"):
                # Ensure message is always a string for step_failed.emit
                if isinstance(message, dict):
                    message_str = json.dumps(message, ensure_ascii=False, indent=2)
                else:
                    message_str = str(message)
                self.step_failed.emit(step_name, message_str)
                error_found = True
                failure_message = message_str

        # Update of the overall result in the database
        if error_found or self.skipped_steps:
            config.db.update_by_id("device_under_test", config.device_under_test_id, {"result": 0})  # type: ignore[attr-defined]
            if failure_message:
                config.db.update_by_id("device_under_test", config.device_under_test_id, {"failure_label": failure_message})  # type: ignore[attr-defined]
        else:
            config.db.update_by_id("device_under_test", config.device_under_test_id, {"result": 1})  # type: ignore[attr-defined]

        device_id = config.device_under_test_id
        output_path = f"rapport_device_{device_id}.pdf"

        if self.generate_report:
            try:
                report = DeviceReport(config.db, int(device_id), debug=config.arg.show_all_logs)  # type: ignore[attr-defined]
                report.fetch_data()
                report.generate_pdf_report(output_path)
                if configuration.VERSION != "DEBUG":
                    os.startfile(output_path)
            except Exception as e:
                error_msg = f"Erreur lors de la génération du rapport ou de l'ouverture du PDF : {e}"
                self.emit_log_message(error_msg, "red")

        self.finished.emit()

    def stop(self):
        """Request the thread to stop execution."""
        self.running = False


class MainWindow(QWidget):
    """Main application window for the CAPSYS DualCap Test Bench GUI."""
    def __init__(self):
        """Initialize the main window, set up UI, and prepare logging and test thread."""
        super().__init__()
        log_dir = os.path.join(tempfile.gettempdir(), "log_banc_de_test_capsys")
        os.makedirs(log_dir, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        self.log_file_path = os.path.join(log_dir, f"log_{today}.txt")
        self.setWindowTitle(f"{config.arg.name} - Version : {config.arg.version} - Commit : {config.arg.hash_git} - Auteur : {config.arg.author}")
        self.setWindowIcon(QIcon(configuration.CURRENTH_PATH + "\\logo-big.png"))

        self.steps_widgets = []
        self.step_infos = []
        self.step_messages = {}
        self.skip_checkboxes = []
        self.test_thread = TestThread()

        self.setup_ui()

        primary_screen = QApplication.primaryScreen()
        if primary_screen is not None:
            screen_geometry = primary_screen.availableGeometry()
        else:
            # Fallback to a default geometry if no screen is available
            from PyQt6.QtCore import QRect
            screen_geometry = QRect(0, 0, 1920, 1080)  # Default fallback size
        
        # Store screen geometry for later use
        self.screen_geometry = screen_geometry
        self.setMinimumWidth(750)
        screen_center_x = screen_geometry.center().x()
        self.move(screen_center_x - self.width() // 2, 0)
        
        # Set initial mode based on command line arguments
        # If script is executed with arguments, use simple mode
        # If script is executed without arguments, use complete mode
        self.has_arguments = len(sys.argv) >= 12
        
        # We'll set the mode after the window is shown using a timer
        if self.has_arguments:
            QTimer.singleShot(0, self.set_simple_mode_with_arguments)
        else:
            # Set fullscreen mode when no arguments and ensure proper window size for complete mode
            QTimer.singleShot(0, self.set_fullscreen_mode)

        # Load the test steps and their info functions
        self.step_infos = [info for _, _, info in self.test_thread.steps]
        
        # Log arguments only in complete mode (will be logged after mode is set)
        if not self.has_arguments:
            for arg in sys.argv:
                self.append_log(arg)
        
        config.printer = PrinterDC(configuration.PRINTER_NAME, debug=config.arg.show_all_logs)
        if not config.printer.connected:
            self.append_log("Erreur de connexion à l'imprimante.", "yellow")

    def set_simple_mode_with_arguments(self):
        """Set simple mode when the script is executed with arguments."""
        if self.has_arguments:
            # Force simple mode when there are arguments
            self.toggle_mode_button.setChecked(True)
            self.toggle_simple_mode()

    def set_fullscreen_mode(self):
        """Set fullscreen mode when the script is executed without arguments."""
        if not self.has_arguments:
            self.showMaximized()  # Set the window to fullscreen
            self.update_window_size()

    def closeEvent(self, a0: QCloseEvent | None):
        """Clean up resources and close database connection when the window is closed."""
        # Stop the test thread if it's running
        if self.test_thread and self.test_thread.isRunning():
            self.test_thread.quit()
            self.test_thread.wait()
        try:
            if hasattr(config, 'db') and config.db is not None:
                config.db.disconnect()
        except Exception as e:
            print(f"Erreur lors de la fermeture de la connexion MySQL : {e}")

        if a0 is not None:
            a0.accept()

    def setup_ui(self):
        """Set up the main UI layout, including step list, log area, and control buttons."""
        main_layout = QVBoxLayout()

        title = QLabel("Étapes de test")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-weight: bold; font-size: 24px;")
        main_layout.addWidget(title)

        # Create a horizontal layout for the steps
        self.steps = self.load_step_names()
        for i, step in enumerate(self.steps):
            row = QHBoxLayout()
            index_label = QLabel(str(i + 1))
            index_label.setFixedWidth(30)
            index_label.setStyleSheet("font-size: 14px; font-weight: bold;")
            row.addWidget(index_label)

            step_str: str = str(step)  # Ensure step is treated as string
            label_step_name = QLabel(step_str.replace('_', ' ').capitalize())
            label_step_name.setStyleSheet("color: white; font-size: 14px;")
            row.addWidget(label_step_name)

            label_status = QLabel("⏳")
            label_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label_status.setFixedWidth(40)
            label_status.setStyleSheet("font-size: 16px;")
            row.addWidget(label_status)

            # Add a skip checkbox for each step (except for initialisation and fin_du_test)
            if step.lower() not in ["initialisation", "fin_du_test"]:
                skip_checkbox = QCheckBox("Sauter")
                skip_checkbox.setFixedWidth(80)
                skip_checkbox.setStyleSheet("font-size: 11px;")
                row.addWidget(skip_checkbox)
                self.skip_checkboxes.append(skip_checkbox)
            else:
                # Add a placeholder widget to maintain layout consistency
                placeholder = QLabel("")
                placeholder.setFixedWidth(80)
                row.addWidget(placeholder)
                self.skip_checkboxes.append(None)  # Add None to maintain index alignment

            # Add an info button for each step
            info_button = QPushButton("ℹ️")
            info_button.clicked.connect(lambda checked, idx=i: self.show_step_info(idx))
            info_button.setFixedWidth(50)
            info_button.setStyleSheet("font-size: 14px;")
            row.addWidget(info_button)

            # Add a message button for each step
            message_button = QPushButton("❗")
            message_button.clicked.connect(lambda checked, idx=i: self.show_step_message(idx))
            message_button.setFixedWidth(50)
            message_button.setStyleSheet("font-size: 14px;")
            row.addWidget(message_button)
            # Initialize the message as empty
            self.step_messages[i] = "Lancer un test pour avoir des informations"

            main_layout.addLayout(row)

            self.steps_widgets.append((label_step_name, label_status))

        # Create a QTextEdit for the log area
        self.log_label = QLabel("LOG")
        self.log_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.log_label.setStyleSheet("font-weight: bold; font-size: 24px;")
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("font-size: 12px; font-family: 'Consolas', monospace;")
        main_layout.addWidget(self.log_label)
        self.log_area.setMinimumHeight(300)
        main_layout.addWidget(self.log_area, stretch=2)

        # Create a button layout
        self.button_layout = QHBoxLayout()
        # Checkbox for PDF report generation
        self.generate_report_checkbox = QCheckBox("Générer le rapport PDF")
        self.generate_report_checkbox.setChecked(False)  # Par défaut décochée
        self.generate_report_checkbox.setStyleSheet("font-size: 12px;")
        self.button_layout.addWidget(self.generate_report_checkbox)
        # Start button
        self.start_button = QPushButton("Démarrer le test")
        self.start_button.clicked.connect(self.start_test)
        self.start_button.setStyleSheet("font-size: 14px; padding: 8px;")
        self.button_layout.addWidget(self.start_button)
        # Stop button
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_test)
        self.stop_button.setStyleSheet("font-size: 14px; padding: 8px;")
        self.button_layout.addWidget(self.stop_button)
        # Toggle simple/complete mode
        # Changed to self.toggle_mode_button
        self.toggle_mode_button = QPushButton("Mode Simple")
        self.toggle_mode_button.setCheckable(True)
        self.toggle_mode_button.clicked.connect(self.toggle_simple_mode)
        self.toggle_mode_button.setStyleSheet("font-size: 12px; padding: 6px;")
        self.button_layout.addWidget(self.toggle_mode_button)
        self.toggle_mode_button.setChecked(False)  # Start in complete mode by default
        # Info button
        self.info_button2 = QPushButton("ℹ️")
        self.info_button2.clicked.connect(self.show_info)
        self.info_button2.setStyleSheet("font-size: 14px; padding: 6px;")
        self.button_layout.addWidget(self.info_button2)
        # Quit button
        self.quit_button = QPushButton("Quitter")
        self.quit_button.clicked.connect(self.close)
        self.quit_button.setStyleSheet("font-size: 14px; padding: 8px;")
        self.button_layout.addWidget(self.quit_button)
        # Add the button layout to the main layout
        main_layout.addLayout(self.button_layout)
        self.setLayout(main_layout)

    def show_step_message(self, idx):
        """Show the stored message for the step at the given index in a dialog box."""
        message = self.step_messages.get(idx, "Aucun message disponible.")  # Retrieves the stored message
        QMessageBox.information(self, f"Message Étape {idx + 1}", message)

    def update_window_size(self):
        """Update window size based on current mode."""
        is_simple = self.toggle_mode_button.isChecked()
        if is_simple:
            # Mode simple : fenêtre redimensionnable et ajustée au contenu
            self.setMaximumHeight(self.screen_geometry.height())  # Use screen height as max
            self.setMinimumHeight(0)  # Remove minimum height constraint
            self.showNormal()  # Exit fullscreen if in fullscreen
            self.adjustSize()  # Resize to minimum needed
        else:
            # Mode complet : toujours en plein écran
            self.setMaximumHeight(self.screen_geometry.height())  # Use screen height as max
            self.showMaximized()  # Always fullscreen in complete mode

    def toggle_simple_mode(self):
        """Toggle between simple and complete display modes for the UI."""
        is_simple = self.toggle_mode_button.isChecked()
        self.toggle_mode_button.setText("Mode Complet" if is_simple else "Mode Simple")
        self.set_section_visibility(not is_simple)
        # Update window size after changing mode
        self.update_window_size()

    def set_section_visibility(self, visible):
        """Set the visibility of the log area and additional buttons based on mode."""
        self.log_label.setVisible(visible)
        self.log_area.setVisible(visible)
        
        # Show/hide skip checkboxes and control buttons based on mode
        for checkbox in self.skip_checkboxes:
            if checkbox is not None:
                checkbox.setVisible(visible)
        
        for i in range(self.button_layout.count()):
            item = self.button_layout.itemAt(i)
            if item is not None:
                widget = item.widget()
                if (
                    widget is not None
                    and widget != self.toggle_mode_button
                    and widget != self.start_button
                    and widget != self.stop_button
                    and widget != self.quit_button
                ):
                    widget.setVisible(visible)

    def load_step_names(self):
        """Load and return the list of step names from the 'steps' directory."""
        steps_folder = os.path.join(os.path.dirname(__file__), "steps")
        step_dirs = sorted(
            d
            for d in os.listdir(steps_folder)
            if os.path.isdir(os.path.join(steps_folder, d))
            and (d.startswith("s") and d[1:].isdigit() or d == "zz")
        )
        step_names = []
        for dir_name in step_dirs:
            dir_path = os.path.join(steps_folder, dir_name)
            py_files = sorted(f for f in os.listdir(dir_path) if f.endswith(".py"))
            for filename in py_files:
                step_names.append(f"{filename[:-3].capitalize()}")
        return step_names

    def show_step_info(self, idx):
        """Show information about the step at the given index using its get_info function."""
        try:
            # Call the info function for the step
            info_text = self.step_infos[idx]()
        except Exception as e:
            info_text = f"Erreur lors de la récupération des infos : {e}"
        QMessageBox.information(self, f"Information Étape {idx + 1}", info_text)

    def show_info(self):
        """Show a legend dialog explaining the color codes and metadata."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton
        from PyQt6.QtGui import QTextCursor, QTextCharFormat, QColor
        from PyQt6.QtCore import Qt
        
        # Create a custom dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Informations")
        dialog.setModal(True)
        dialog.resize(400, 300)
        
        layout = QVBoxLayout()
        
        # Create a text widget for colored display
        info_text = QTextEdit()
        info_text.setReadOnly(True)
        
        # Add the information with colors
        cursor = info_text.textCursor()
        
        # Version info
        version_format = QTextCharFormat()
        version_format.setForeground(QColor("#ff00ff"))  # Purple
        version_format.setFontWeight(700)
        cursor.insertText("Version : ", version_format)
        
        normal_format = QTextCharFormat()
        normal_format.setForeground(QColor("#ffffff"))
        cursor.insertText(f"{configuration.VERSION}\n", normal_format)
        
        cursor.insertText("Auteur : ", version_format)
        cursor.insertText(f"{configuration.AUTHOR}\n\n", normal_format)
        
        # Color legend
        legend_title_format = QTextCharFormat()
        legend_title_format.setForeground(QColor("#ffffff"))
        legend_title_format.setFontWeight(700)
        cursor.insertText("Légende des couleurs :\n\n", legend_title_format)
        
        color_entries = [
            ("Blanc", "#ffffff", "Message général"),
            ("Jaune", "#ffff00", "Warning"),
            ("Cyan", "#00ffff", "Nom d'étapes de test"),
            ("Bleu", "#4da6ff", "Message provenant d'une étape de test"),
            ("Vert", "#00ff00", "Succès"),
            ("Orange", "#ffa500", "Étape sautée"),
            ("Rouge", "#ff4444", "Échec")
        ]
        
        for color_name, color_code, description in color_entries:
            color_format = QTextCharFormat()
            color_format.setForeground(QColor(color_code))
            cursor.insertText(f"{color_name}", color_format)
            cursor.insertText(f" : {description}\n", normal_format)
        
        layout.addWidget(info_text)
        
        # Add OK button
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(dialog.accept)
        layout.addWidget(ok_button)
        
        dialog.setLayout(layout)
        dialog.exec()

    def start_test(self):
        """Start the test sequence by launching the test thread and resetting the UI."""
        if self.test_thread and self.test_thread.isRunning():
            self.log_area.append("Un test est déjà en cours...")
            return

        self.log_area.clear()
        self.reset_steps()

        # Get skipped steps from checkboxes
        skipped_steps = set()
        for i, checkbox in enumerate(self.skip_checkboxes):
            if checkbox is not None and checkbox.isChecked():
                skipped_steps.add(i)

        generate_report = self.generate_report_checkbox.isChecked()
        self.test_thread = TestThread(skipped_steps, generate_report)
        self.test_thread.update_step.connect(self.update_step_status)
        self.test_thread.log_message.connect(self.append_log)
        self.test_thread.finished.connect(self.test_finished)
        self.test_thread.step_failed.connect(self.handle_step_failure)
        self.test_thread.start()

    def handle_step_failure(self, step_name, message):
        """Display a critical error dialog when a test step fails."""
        # Affiche uniquement les infos si présentes
        msg_to_show = message
        obj = None
        if isinstance(message, str):
            try:
                obj = json.loads(message)
            except Exception:
                obj = None
        elif isinstance(message, dict):
            obj = message
        if isinstance(obj, dict) and "infos" in obj and isinstance(obj["infos"], list):
            msg_to_show = "\n".join([str(v) for v in obj["infos"]])
        elif isinstance(obj, dict):
            msg_to_show = ", ".join([f"{k}: {v}" for k, v in obj.items()])
        QMessageBox.critical(self, f"Erreur", f"L'étape '{step_name[3:]}' a échoué :\n{msg_to_show}")

    def stop_test(self):
        """Stop the test thread and run the cleanup step if necessary."""
        if not (self.test_thread and self.test_thread.isRunning()):
            self.append_log("Aucun test en cours à arrêter.", "yellow")
            return
        self.test_thread.stop()  # Gentle request to stop
        # Wait up to 5 seconds for the thread to terminate
        finished = self.test_thread.wait(5000)
        if not finished:
            self.append_log("Arrêt forcé du thread de test après 5s...", "yellow")
            self.test_thread.terminate()
            self.test_thread.wait()
        # Run the cleanup step Fin_du_test.py
        try:
            step_path = os.path.join(os.path.dirname(__file__), "steps", "zz", "Fin_du_test.py")
            spec = importlib.util.spec_from_file_location("Fin_du_test", step_path)
            if spec is not None and spec.loader is not None:
                fin_du_test = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(fin_du_test)
                if hasattr(fin_du_test, "run_step"):
                    success, message = fin_du_test.run_step(self.append_log, config)
                    color = "green" if success == 0 else ("yellow" if success == 2 else "red")
                    self.append_log(f"[Fin_du_test] {message}", color)
                else:
                    self.append_log("La fonction run_step n'a pas été trouvée dans Fin_du_test.py.", "red")
            else:
                self.append_log("Impossible de charger le module Fin_du_test.py.", "red")
        except Exception as e:
            self.append_log(f"Erreur lors de l'exécution de Fin_du_test.py : {e}", "red")

    def reset_steps(self):
        """Reset the step status indicators in the UI to their initial state."""
        for label_step_name, label_status in self.steps_widgets:
            label_step_name.setStyleSheet("color: white; font-size: 14px;")
            label_status.setText("⏳")

    def update_step_status(self, idx, status, success, message=""):
        """Update the status and color of a step in the UI and store its message."""
        label_step_name, label_status = self.steps_widgets[idx]
        label_status.setText(status)
        if success == 0:
            label_step_name.setStyleSheet("color: green; font-size: 14px;")
        elif "Étape en cours" in message:
            label_step_name.setStyleSheet("color: yellow; font-size: 14px;")
        elif "Étape sautée par l'utilisateur" in message:
            label_step_name.setStyleSheet("color: orange; font-size: 14px;")
        else:
            label_step_name.setStyleSheet("color: red; font-size: 14px;")

        # Store the step message
        self.step_messages[idx] = message
        # self.append_log(f"Message de l'étape {idx + 1} : {message}", "blue")

    def append_log(self, message, color="white"):
        """Append a log message to the log area and save it to the log file."""
        from PyQt6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor = self.log_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Format for the timestamp (always in gray)
        timestamp_format = QTextCharFormat()
        timestamp_format.setForeground(QColor("#888888"))
        cursor.insertText(f"[{now}] ", timestamp_format)


        color_map = {
            "white": "#ffffff",
            "yellow": "#ffff00",
            "cyan": "#00ffff",
            "blue": "#4da6ff",
            "green": "#00ff00",
            "orange": "#ffa500",
            "red": "#ff4444",
            "purple": "#ff00ff"
        }

        # Custom display for dict with 'infos' key
        if isinstance(message, str):
            try:
                obj = json.loads(message)
            except Exception:
                obj = None
        elif isinstance(message, dict):
            obj = message
        else:
            obj = None

        # Determine color for dict display
        dict_color = color_map["green"] if color == "green" else (color_map["red"] if color == "red" else color_map["blue"])

        if isinstance(obj, dict) and "infos" in obj and isinstance(obj["infos"], list):
            message_format = QTextCharFormat()
            message_format.setForeground(QColor(dict_color))
            message_format.setFontFamily("Consolas")
            message_format.setFontPointSize(12)
            for v in obj["infos"]:
                cursor.insertText(f"{v}\n", message_format)
            plain_message = f"[{now}] " + "\n".join([str(v) for v in obj["infos"]]) + "\n"
        elif isinstance(obj, dict):
            message_format = QTextCharFormat()
            message_format.setForeground(QColor(dict_color))
            message_format.setFontFamily("Consolas")
            message_format.setFontPointSize(12)
            for k, v in obj.items():
                cursor.insertText(f"{k} : {v}\n", message_format)
            plain_message = f"[{now}] " + "\n".join([f"{k} : {v}" for k, v in obj.items()]) + "\n"
        else:
            message_format = QTextCharFormat()
            message_color = color_map.get(color, "#ffffff")
            message_format.setForeground(QColor(message_color))
            message_format.setFontPointSize(12)
            cursor.insertText(f"{message}\n", message_format)
            plain_message = f"[{now}] {message}\n"

        self.log_area.setTextCursor(cursor)
        self.log_area.ensureCursorVisible()

        # Saving to file
        try:
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(plain_message)
        except Exception as e:
            print(f"Erreur lors de l'écriture du log : {e}")

    def test_finished(self):
        """Handle the end of the test sequence, update the log, and store results in the database."""
        from PyQt6.QtGui import QTextCursor, QTextCharFormat, QColor
        
        all_success = all(label_status.text() == "✅" for _, label_status in self.steps_widgets)
        any_error = any(label_status.text() == "❌" for _, label_status in self.steps_widgets)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if all_success:
            color = "green"
            message = "Test OK"
        elif any_error:
            color = "red"
            message = "Test NOK"
        else:
            color = "yellow"
            message = "Test interrompu ou étape sautée"

        # Add the final message with color formatting
        cursor = self.log_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # Format for the timestamp
        timestamp_format = QTextCharFormat()
        timestamp_format.setForeground(QColor("#888888"))
        cursor.insertText(f"[{now}] ", timestamp_format)
        
        # Format for the final message
        message_format = QTextCharFormat()
        color_map = {
            "green": "#00ff00",
            "red": "#ff4444",
            "yellow": "#ffff00"
        }
        message_color = color_map.get(color, "#ffffff")
        message_format.setForeground(QColor(message_color))
        cursor.insertText(f"{message}\n\n", message_format)
        
        self.log_area.setTextCursor(cursor)
        self.log_area.ensureCursorVisible()
        
        log_text = self.log_area.toPlainText()
        try:
            config.db.create("log", {"device_under_test_id": config.device_under_test_id, "value": log_text})  # type: ignore[attr-defined]
        except Exception as e:
            self.append_log(f"Erreur lors de l'enregistrement du log en BDD : {e}", "red")


def main():
    """Main function to initialize the application and start the GUI"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )

    # This helps with PyInstaller and multiprocessing issues
    import multiprocessing
    multiprocessing.freeze_support()
    
    global config  # Declare config as global
    
    if os.name == "nt" and sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    """Set up the database"""
    if len(sys.argv) < 12:
        print("Aucun argument fourni, utilisation des paramètres par défaut pour le débogage.")
        # config.arg.operator = "Thomas GERARDIN"
        # config.arg.commande = "1"
        # config.arg.of = "1"
        # config.arg.article = "radar"
        # config.arg.indice = "1"
        # config.arg.product_list_id = "4"
        # config.arg.user = "root"
        # config.arg.password = "root"
        # config.arg.host = "127.0.0.1"
        # config.arg.port = "3306"
        # config.arg.database = "capsys_db_bdt"
    else:
        print("Arguments fournis, utilisation des paramètres de la ligne de commande.")
        config.arg.operator = sys.argv[1]
        config.arg.commande = sys.argv[2]
        config.arg.of = sys.argv[3]
        config.arg.article = sys.argv[4]
        config.arg.indice = sys.argv[5]
        config.arg.product_list_id = sys.argv[6]
        config.arg.user = sys.argv[7]
        config.arg.password = sys.argv[8]
        config.arg.host = sys.argv[9]
        config.arg.port = sys.argv[10]
        config.arg.database = sys.argv[11]

    # Establish database connection
    config.db_config = DatabaseConfig(
        user=config.arg.user,
        password=config.arg.password,
        host=config.arg.host,
        port=int(config.arg.port),
        database=config.arg.database,
    )
    config.db = GenericDatabaseManager(config.db_config, debug=config.arg.show_all_logs)
    config.db.connect()
    
    """Launch the GUI"""
    app = QApplication(sys.argv)
    
    # Define application style with a modern dark theme
    app.setStyle('Fusion')
    
    # Set a modern dark palette
    from PyQt6.QtGui import QPalette, QColor
    
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(0, 0, 0))
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
    dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
    
    app.setPalette(dark_palette)
    

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()