import csv
import os
import serial
import time

class PrinterConnection:
    def __init__(self, port="COM3", baudrate=115200, timeout=5):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
    
    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            print(f"Connected to printer on {self.port} at {self.baudrate} baud.")
            time.sleep(2)  # Wait a moment to allow the printer to initialize
        except serial.SerialException as e:
            print(f"Error connecting to printer: {e}")
            return False
        return True

    def send_gcode(self, gcode):
        if not self.ser:
            print("No connection to printer.")
            return
        try:
            gcode_command = gcode.strip() + '\n'
            self.ser.write(gcode_command.encode())
            print(f"Sent G-code: {gcode}")
        except Exception as e:
            print(f"Failed to send G-code: {e}")

    def read_response(self):
        try:
            response = self.ser.readline().decode('utf-8').strip()
            if response:
                print(f"Printer Response: {response}")
            else:
                print("No response received from printer.")
            return response
        except Exception as e:
            print(f"Failed to read response: {e}")
            return None

    def close(self):
        if self.ser:
            self.ser.close()
            print(f"Closed connection to {self.port}.")

def parse_temperatures(response):
    """
    Parses the extruder and bed temperature from the printer response.
    
    :param response: Printer's response string from M105 G-code
    :return: Extruder and bed temperature as floats (or None if not found)
    """
    extruder_temp, bed_temp = None, None
    if response and "T:" in response and "B:" in response:
        temp_data = response.split(" ")
        for data in temp_data:
            if data.startswith("T:"):
                extruder_temp = float(data.split(":")[1].split("/")[0])
            if data.startswith("B:"):
                bed_temp = float(data.split(":")[1].split("/")[0])
    return extruder_temp, bed_temp

def log_print_data(temperature, bed_temperature, speed, layer_height, infill_percentage, print_duration, quality_score):
    """
    Logs the print data into a CSV file.
    
    :param temperature: Extruder temperature in °C
    :param bed_temperature: Bed temperature in °C
    :param speed: Print speed in mm/s
    :param layer_height: Layer height in mm
    :param infill_percentage: Infill density in %
    :param print_duration: Duration of the print in seconds
    :param quality_score: Quality score (1-10 or 0-1 scale)
    """
    file_path = "print_data.csv"
    
    file_exists = os.path.isfile(file_path)
    
    with open(file_path, mode='a', newline='') as file:
        writer = csv.writer(file)
        
        if not file_exists:
            writer.writerow(["Temperature", "Bed_Temperature", "Speed", "Layer_Height", "Infill_Percentage", "Print_Duration", "Quality_Score"])
        
        writer.writerow([temperature, bed_temperature, speed, layer_height, infill_percentage, print_duration, quality_score])

    print(f"Print data logged: {temperature}°C (Extruder), {bed_temperature}°C (Bed), {speed}mm/s, {layer_height}mm, {infill_percentage}%, {print_duration}s, Quality: {quality_score}")



