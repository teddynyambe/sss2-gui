#!/usr/bin/env python3
import serial
import sys
import argparse
import threading

def read_from_device(ser):
    """Thread to continuously read from serial and print to console."""
    while True:
        try:
            line = ser.readline().decode(errors='ignore')
            if line:
                print(f"\r[SSS2] {line}", end='')
        except serial.SerialException:
            print("\n[!] Serial connection lost.")
            break
        except Exception as e:
            print(f"\n[!] Error reading: {e}")
            break

def main():
    parser = argparse.ArgumentParser(description="SSS2 Serial CLI")
    parser.add_argument('--port', default='/dev/cu.usbmodem40768801', help='Serial port (default: /dev/cu.usbmodem40768801)')
    parser.add_argument('--baud', type=int, default=115200, help='Baud rate (default: 115200)')
    args = parser.parse_args()

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.5)
        print(f"[+] Connected to {args.port} at {args.baud} baud.")
    except serial.SerialException as e:
        print(f"[!] Failed to open port: {e}")
        sys.exit(1)

    # Start reader thread
    threading.Thread(target=read_from_device, args=(ser,), daemon=True).start()

    try:
        while True:
            cmd = input(">>> ")
            if cmd.lower() in ['exit', 'quit']:
                print("[*] Exiting...")
                break
            ser.write((cmd + '\r\n').encode())
    except KeyboardInterrupt:
        print("\n[*] Ctrl+C detected. Exiting...")
    finally:
        ser.close()

if __name__ == "__main__":
    main()
