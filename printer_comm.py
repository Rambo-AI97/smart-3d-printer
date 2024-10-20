import serial
import time
import os
import csv
import tkinter as tk
from tkinter import Tk, Text, Scrollbar, filedialog
from tkinter.filedialog import askopenfilename
from threading import Thread


class PrinterConnection:
    def __init__(self, app, port="COM3", baudrate=115200, timeout=5):
        self.app = app  # Store the app instance
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
    
    def connect(self):
        """Establish a serial connection to the printer."""
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            print(f"Connected to printer on {self.port} at {self.baudrate} baud.")
            time.sleep(2)  # Wait a moment to allow the printer to initialize
        except serial.SerialException as e:
            print(f"Error connecting to printer: {e}")
            return False
        return True
    def log_to_window(self, message):
        """Display a log message in the text window."""
        self.app.log_message(message)

    def set_temperatures(self, extruder_temp=200, bed_temp=60):
        """Send the G-code to set extruder and bed temperatures, and wait until they reach the desired values."""
        if not self.ser:
            print("No connection to printer.")
            return

        try:
            # Set and wait for bed and extruder temperatures
            self.ser.write(f'M140 S{bed_temp}\n'.encode())  # Set bed temp
            print(f"Setting bed temperature to {bed_temp}°C...")
            self.ser.write(f'M190 S{bed_temp}\n'.encode())  # Wait for bed to reach temp
            bed_response = self.ser.readline().decode('utf-8').strip()
            print(f"Bed Response: {bed_response}")

            # Try setting the extruder temperature
            self.ser.write(f'M104 S{extruder_temp}\n'.encode())  # Set extruder temp
            print(f"Setting extruder temperature to {extruder_temp}°C...")
            time.sleep(2)  # Wait a bit before checking the response
            self.ser.write(f'M109 S{extruder_temp}\n'.encode())  # Wait for extruder to reach temp
            extruder_response = self.ser.readline().decode('utf-8').strip()
            print(f"Extruder Response: {extruder_response}")
            # Add an initial extrusion command
            self.ser.write('G1 F1800 E10\n'.encode())  # Extrude 10mm of filament


            # Retry if the temperature wasn't set properly
            if "/0.00" in extruder_response:  # Check if the extruder target temp is still 0
                print("Retrying extruder temperature command...")
                self.ser.write(f'M104 S{extruder_temp}\n'.encode())
                time.sleep(2)  # Wait again
                self.ser.write(f'M109 S{extruder_temp}\n'.encode())
                extruder_response = self.ser.readline().decode('utf-8').strip()
                print(f"Extruder Response After Retry: {extruder_response}")

        except Exception as e:
            print(f"Failed to set temperatures: {e}")


    def send_gcode_with_progress(self, gcode_file, output_file="print_data.csv"):
        """Send a G-code file line by line to the printer, with progress updates and data logging."""
        if not self.ser:
            self.log_to_window("No connection to printer.")
            return

        try:
            total_lines = sum(1 for _ in open(gcode_file, 'r'))  # Get total number of lines in the G-code file
            self.log_to_window(f"Total lines in G-code file: {total_lines}")

            start_time = time.time()  # Record the start time

            # Set temperatures before starting the print
            self.set_temperatures(extruder_temp=200, bed_temp=60)

            # Open the CSV file for logging data
            with open(output_file, 'a', newline='') as csvfile:
                fieldnames = ['line_number', 'gcode_command', 'printer_response', 'progress', 'elapsed_time', 'remaining_time']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                # Write header if it's a new file
                if csvfile.tell() == 0:
                    writer.writeheader()

                # Start reading and sending G-code lines
                with open(gcode_file, 'r') as file:
                    for i, line in enumerate(file, start=1):
                        gcode_command = line.strip()
                        if gcode_command:
                            # Send G-code line to printer
                            self.ser.write((gcode_command + '\n').encode())
                            time.sleep(0.1)  # Give the printer time to process each line
                            response = self.ser.readline().decode('utf-8').strip()  # Read response

                            # Log extrusion commands and other G-code
                            if 'E' in gcode_command:
                                self.log_to_window(f"Extrusion Command Sent: {gcode_command}")
                            else:
                                self.log_to_window(f"Command Sent: {gcode_command}")

                            # Calculate progress and timing
                            elapsed_time = time.time() - start_time
                            progress = (i / total_lines) * 100
                            estimated_total_time = (elapsed_time / i) * total_lines
                            remaining_time = estimated_total_time - elapsed_time

                            # Print progress updates
                            if i % (total_lines // 20) == 0:
                                self.log_to_window(f"Progress: {progress:.2f}% complete")
                                self.log_to_window(f"Elapsed Time: {elapsed_time / 60:.2f} minutes")
                                self.log_to_window(f"Estimated Remaining Time: {remaining_time / 60:.2f} minutes")
                                self.log_to_window(f"Printer Response: {response}")

                            # Log the data to the CSV file
                            writer.writerow({
                                'line_number': i,
                                'gcode_command': gcode_command,
                                'printer_response': response,
                                'progress': progress,
                                'elapsed_time': elapsed_time,
                                'remaining_time': remaining_time
                            })

            # Final summary
            total_elapsed_time = time.time() - start_time
            self.log_to_window(f"Printing complete. Total time: {total_elapsed_time / 60:.2f} minutes")

        except Exception as e:
            self.log_to_window(f"Failed to send G-code: {e}")
    def home_and_cooldown(self):
        """Send the printer to its home position and cool down the extruder and bed to standby levels."""
        if not self.ser:
            self.log_to_window("No connection to printer.")
            return

        try:
            # Home the printer (move to the default home position)
            self.ser.write('G28\n'.encode())  # G28 is the home command for all axes
            self.log_to_window("Sending printer to home position...")
            response = self.ser.readline().decode('utf-8').strip()
            self.log_to_window(f"Home Response: {response}")
            
            time.sleep(2)  # Wait for homing to finish

            # Cool down the extruder and bed
            self.ser.write('M104 S0\n'.encode())  # Set extruder temp to 0°C
            self.log_to_window("Cooling down extruder to 0°C...")
            self.ser.write('M140 S0\n'.encode())  # Set bed temp to 0°C
            self.log_to_window("Cooling down bed to 0°C...")
            
            response = self.ser.readline().decode('utf-8').strip()
            self.log_to_window(f"Cooldown Response: {response}")

        except Exception as e:
            self.log_to_window(f"Failed to home and cool down: {e}")

    class PrinterApp(tk.Tk):
        def __init__(self):
            super().__init__()
            self.title("3D Printer Monitor")
            self.geometry("600x400")

            # Create a text widget to display logs
            self.text_widget = Text(self, wrap=tk.WORD, height=20, width=80)
            self.text_widget.pack(padx=10, pady=10)

            # Create a scroll bar for the text widget
            scroll_bar = Scrollbar(self.text_widget)
            self.text_widget.config(yscrollcommand=scroll_bar.set)
            scroll_bar.pack(side=tk.RIGHT, fill=tk.Y)

        def log_message(self, message):
            """Log a message to the text widget."""
            self.text_widget.insert(tk.END, message + "\n")
            self.text_widget.see(tk.END)  # Auto-scroll to the bottom
        def close(self):
            """Close the serial connection to the printer."""
            if self.ser:
                self.ser.close()
                print(f"Closed connection to {self.port}.")

def select_gcode_file():
    """Open a file dialog to select the G-code file."""
    Tk().withdraw()  # Hide the Tkinter root window
    file_path = askopenfilename(
        title="Select the G-code File",
        filetypes=[("G-code Files", "*.gcode")]
    )
    if file_path:
        print(f"Selected file: {file_path}")
        return file_path
    else:
        print("No file selected")
        return None
    
# Define the PrinterApp class before using it in the main block
class PrinterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("3D Printer Monitor")
        self.geometry("600x400")

        # Create a text widget to display logs
        self.text_widget = Text(self, wrap=tk.WORD, height=20, width=80)
        self.text_widget.pack(padx=10, pady=10)

        # Create a scroll bar for the text widget
        scroll_bar = Scrollbar(self.text_widget)
        self.text_widget.config(yscrollcommand=scroll_bar.set)
        scroll_bar.pack(side=tk.RIGHT, fill=tk.Y)

    def log_message(self, message):
        """Log a message to the text widget."""
        self.text_widget.insert(tk.END, message + "\n")
        self.text_widget.see(tk.END)  # Auto-scroll to the bottom

if __name__ == "__main__":
    # Initialize the Tkinter app
    app = PrinterApp()

    # Select the G-code file to send
    gcode_file = select_gcode_file()

    if gcode_file:
        # Initialize and connect to the printer, passing the app instance
        printer = PrinterConnection(app, port="COM3", baudrate=115200)
        if printer.connect():
            # Run the G-code sending process in a separate thread to keep the GUI responsive
            Thread(target=printer.send_gcode_with_progress, args=(gcode_file,)).start()
            
            # Home and cool down the printer after printing
            Thread(target=printer.home_and_cooldown).start()
    
    # Start the Tkinter GUI loop
    app.mainloop()





#