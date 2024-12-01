import tkinter as tk
from tkinter import ttk, filedialog
import json
from TopologyTest import TopologyTest
from pathlib import Path

class TopologyTestGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Topology Test Configuration")
        
        # Load config file and get dataset types
        self.config_file = self.load_config()
        # Update this line to explicitly get the keys from dataset_rules
        self.dataset_types = list(self.config_file.get('dataset_rules', {}).keys())
        if not self.dataset_types:
            print("Warning: No dataset types found in config file")
        
        # Create main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # File Selection Section
        self.create_file_selection_section(main_frame)
        
        # Topology Checks Section
        self.create_topology_checks_section(main_frame)
        
        # Tolerance Settings Section
        self.create_tolerance_settings_section(main_frame)
        
        # Run Button
        ttk.Button(main_frame, text="Run Topology Tests", command=self.run_tests).grid(
            row=100, column=0, columnspan=3, pady=20)

    def load_config(self):
        """Load the configuration file."""
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
                print("Loaded config file:")
                print("Dataset rules:", config.get('dataset_rules', {}).keys())
                return config
        except FileNotFoundError:
            print("Config file not found!")
            return {"global_settings": {"enabled_checks": {}, "tolerances": {}}, "dataset_rules": {}}
        except json.JSONDecodeError:
            print("Error parsing config.json!")
            return {"global_settings": {"enabled_checks": {}, "tolerances": {}}, "dataset_rules": {}}

    def create_file_selection_section(self, parent):
        # File Selection Frame
        file_frame = ttk.LabelFrame(parent, text="Input Files", padding="5")
        file_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        # Add File Button
        ttk.Button(file_frame, text="Add File", command=self.add_file_row).grid(
            row=0, column=0, pady=5)
        
        self.file_rows_frame = ttk.Frame(file_frame)
        self.file_rows_frame.grid(row=1, column=0, sticky=(tk.W, tk.E))
        
        self.file_rows = []
        self.add_file_row()  # Add initial row

    def add_file_row(self):
        row_frame = ttk.Frame(self.file_rows_frame)
        row_frame.grid(row=len(self.file_rows), column=0, pady=2)
        
        # File path entry
        path_var = tk.StringVar()
        path_entry = ttk.Entry(row_frame, textvariable=path_var, width=50)
        path_entry.grid(row=0, column=0, padx=5)
        
        # Browse button
        ttk.Button(row_frame, text="Browse", 
                command=lambda: self.browse_file(path_var)).grid(row=0, column=1, padx=5)
        
        # Dataset type dropdown
        type_var = tk.StringVar()
        print("Available dataset types:", self.dataset_types)  # Debug print
        type_dropdown = ttk.Combobox(row_frame, textvariable=type_var, 
                                values=self.dataset_types, width=15)
        if self.dataset_types:  # Set default value if available
            type_dropdown.set(self.dataset_types[0])
        type_dropdown.grid(row=0, column=2, padx=5)
        
        # Remove button
        ttk.Button(row_frame, text="Remove", 
                command=lambda: self.remove_file_row(row_frame)).grid(row=0, column=3, padx=5)
        
        self.file_rows.append((row_frame, path_var, type_var))

    def remove_file_row(self, row_frame):
        if len(self.file_rows) > 1:  # Keep at least one row
            row_frame.grid_remove()
            self.file_rows = [(f, p, t) for f, p, t in self.file_rows if f != row_frame]
            self.reorder_rows()

    def reorder_rows(self):
        for i, (frame, _, _) in enumerate(self.file_rows):
            frame.grid(row=i, column=0)

    def create_topology_checks_section(self, parent):
        # Topology Checks Frame
        checks_frame = ttk.LabelFrame(parent, text="Topology Checks", padding="5")
        checks_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        # Get enabled checks from config
        enabled_checks = self.config_file.get('global_settings', {}).get('enabled_checks', {})
        
        # Create checkboxes for each check
        self.check_vars = {}
        checks = ["intersections", "self_intersections", "gaps", "dangles", 
                 "overlaps", "containment"]
        
        for i, check in enumerate(checks):
            var = tk.BooleanVar(value=enabled_checks.get(check, True))
            self.check_vars[check] = var
            ttk.Checkbutton(checks_frame, text=check.replace('_', ' ').title(), 
                           variable=var).grid(row=i//3, column=i%3, padx=10, pady=5)

    def create_tolerance_settings_section(self, parent):
        # Tolerance Settings Frame
        tolerance_frame = ttk.LabelFrame(parent, text="Tolerance Settings (meters)", padding="5")
        tolerance_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        # Get tolerances from config
        tolerances = self.config_file.get('global_settings', {}).get('tolerances', {})
        
        # Create entry fields for each tolerance
        self.tolerance_vars = {}
        tolerances_list = [("gap", "Gap Tolerance"), ("overlap", "Overlap Tolerance")]
        
        for i, (key, label) in enumerate(tolerances_list):
            ttk.Label(tolerance_frame, text=label).grid(row=i, column=0, padx=5, pady=5)
            var = tk.StringVar(value=str(tolerances.get(key, 0.001)))
            self.tolerance_vars[key] = var
            ttk.Entry(tolerance_frame, textvariable=var, width=10).grid(
                row=i, column=1, padx=5, pady=5)

    def browse_file(self, path_var):
        filename = filedialog.askopenfilename(
            filetypes=[("GeoJSON files", "*.geojson"), ("All files", "*.*")])
        if filename:
            path_var.set(filename)

    def run_tests(self):
        # Update config with current settings
        self.update_config()
        
        # Run topology tests for each file
        for _, path_var, type_var in self.file_rows:
            if path_var.get() and type_var.get():
                checker = TopologyTest(
                    geojson_file=path_var.get(),
                    dataset_type=type_var.get(),
                    config_file='config.json'
                )
                
                results = checker.validate_topology()
                output_files = checker.save_topology_results(results)
                
                # Show results in a new window
                self.show_results(checker.report_summary(), output_files)

    def update_config(self):
        # Update enabled checks
        self.config_file['global_settings']['enabled_checks'] = {
            check: var.get() for check, var in self.check_vars.items()
        }
        
        # Update tolerances
        self.config_file['global_settings']['tolerances'] = {
            key: float(var.get()) for key, var in self.tolerance_vars.items()
        }
        
        # Save updated config
        with open('config.json', 'w') as f:
            json.dump(self.config_file, f, indent=4)

    def show_results(self, summary, output_files):
        results_window = tk.Toplevel(self.root)
        results_window.title("Topology Test Results")
        
        # Create text widget for results
        text_widget = tk.Text(results_window, wrap=tk.WORD, width=60, height=20)
        text_widget.grid(row=0, column=0, padx=10, pady=10)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(results_window, orient=tk.VERTICAL, 
                                command=text_widget.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        text_widget['yscrollcommand'] = scrollbar.set
        
        # Insert results
        text_widget.insert(tk.END, summary + "\n\nOutput files:\n")
        for check_type, file_path in output_files.items():
            text_widget.insert(tk.END, f"{check_type}: {file_path}\n")
        
        text_widget.configure(state='disabled')  # Make read-only

def main():
    root = tk.Tk()
    app = TopologyTestGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()