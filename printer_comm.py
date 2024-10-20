import serial
import time

class PrinterConnection:
    def __init__(self, port="COM3", baudrate=115200, timeout=5):
        """
        Initializes the connection to the 3D printer.
        
        :param port: The serial port to use (e.g., "COM3" or "/dev/ttyUSB0")
        :param baudrate: The baud rate for the connection (115200 or 250000)
        :param timeout: How long to wait for a response from the printer
        """
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
    def send_gcode_with_progress(self, gcode_file):
        """Send a G-code file line by line to the printer, with progress updates."""
        if not self.ser:
            print("No connection to printer.")
            return

        try:
            total_lines = sum(1 for _ in open(gcode_file, 'r'))  # Get total number of lines in the G-code file
            print(f"Total lines in G-code file: {total_lines}")

            start_time = time.time()  # Record the start time

            with open(gcode_file, 'r') as file:
                for i, line in enumerate(file, start=1):
                    gcode_command = line.strip()
                    if gcode_command:
                        self.ser.write((gcode_command + '\n').encode())  # Send G-code line
                        time.sleep(0.1)  # Give the printer time to process each line
                        response = self.ser.readline().decode('utf-8').strip()  # Read response

                        # Print progress every 5% of the file
                        if i % (total_lines // 20) == 0:
                            elapsed_time = time.time() - start_time
                            progress = (i / total_lines) * 100
                            estimated_total_time = (elapsed_time / i) * total_lines
                            remaining_time = estimated_total_time - elapsed_time

                            print(f"Progress: {progress:.2f}% complete")
                            print(f"Elapsed Time: {elapsed_time / 60:.2f} minutes")
                            print(f"Estimated Remaining Time: {remaining_time / 60:.2f} minutes")
                            print(f"Printer Response: {response}")

            # Final summary
            total_elapsed_time = time.time() - start_time
            print(f"Printing complete. Total time: {total_elapsed_time / 60:.2f} minutes")

        except Exception as e:
            print(f"Failed to send G-code: {e}")

    def send_gcode(self, gcode_file):
        """Send a G-code file line by line to the printer."""
        if not self.ser:
            print("No connection to printer.")
            return

        try:
            with open(gcode_file, 'r') as file:
                for line in file:
                    gcode_command = line.strip()
                    if gcode_command:
                        self.ser.write((gcode_command + '\n').encode())  # Send G-code line
                        time.sleep(0.1)  # Give the printer time to process each line
                        response = self.ser.readline().decode('utf-8').strip()  # Read response
                        print(f"Printer Response: {response}")
        except Exception as e:
            print(f"Failed to send G-code: {e}")

    def read_response(self):
        """
        Read a response from the printer after sending a G-code command.
        """
        try:
            response = self.ser.readline().decode('utf-8').strip()
            if response:
                print(f"Printer Response: {response}")
            else:
                print("No response received from printer.")
        except Exception as e:
            print(f"Failed to read response: {e}")

    def close(self):
        """Close the serial connection to the printer."""
        if self.ser:
            self.ser.close()
            print(f"Closed connection to {self.port}.")

    def select_gcode_file(): 
        #"""Open a file dialog to select the G-code file."""
        Tk().withdraw()  # Close the root window from tkinter
        gcode_file = askopenfilename(
            filetypes=[("G-code Files", "*.gcode")],
            title="Select G-code File"
        )
        return gcode_file

#