import serial

# Replace 'COM3' with your printer's serial port
printer_port = "COM3"

# Set up the serial connection with the correct baud rate (115200 for most 3D printers)
ser = serial.Serial(printer_port, 115200, timeout=5)

# Send a G-code command to get the printer temperature
ser.write(b"M105\n")  # M105 is the command to request current temperature

# Read the response from the printer
response = ser.readline().decode('utf-8').strip()
print(f"Printer Response: {response}")

# Close the serial connection
ser.close()
