#!/usr/bin/env python3
"""Read the iOS console straight off the phone's CDC-ACM port.

The kernel presents itself as a CDC-ACM device (VID 0x1209, PID 0x0001, the
pid.codes test pair) and pushes the console ring out of bulk IN as a plain
byte stream, so whatever the COM port delivers is exactly the text the
screen shows.  Windows binds usbser.sys to it from the box -- its
usbser.inf matches "USB\\Class_02&SubClass_02&Prot_01", which is what
patch 0101 describes the comm interface as -- so no extra driver is needed.

    python console_log.py                 # auto-detect the port, write ios-console.log
    python console_log.py COM7 out.log    # use a specific port / file

Survives the device disappearing (reboot, fastboot) and keeps retrying.
Requires pyserial (pip install pyserial).
"""
import glob
import os
import sys
import time

import serial
from serial.tools import list_ports

VID = 0x1209          # pid.codes test VID the kernel presents
PID = 0x0001

OUT = sys.argv[2] if len(sys.argv) > 2 else "ios-console.log"


def find_port(preferred=None):
    if preferred:
        return preferred
    for p in list_ports.comports():
        if (p.vid, p.pid) == (VID, PID):
            return p.device
    cands = [p.device for p in list_ports.comports()
             if "USB 串行" in (p.description or "") or "USB Serial" in (p.description or "")]
    return cands[0] if cands else None


def main():
    want = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else None
    out = open(OUT, "ab", buffering=0)
    print("writing to %s (Ctrl-C to stop)" % os.path.abspath(OUT), flush=True)
    total = 0
    while True:
        port = find_port(want)
        if not port:
            time.sleep(1.0)
            continue
        try:
            ser = serial.Serial(port, 115200, timeout=0.5)
        except Exception as e:
            print("open %s failed: %s" % (port, e), flush=True)
            time.sleep(1.0)
            continue
        print("=== %s open ===" % port, flush=True)
        try:
            while True:
                buf = ser.read(4096)
                if buf:
                    out.write(buf)
                    total += len(buf)
                    sys.stdout.write(buf.decode("utf-8", "replace"))
                    sys.stdout.flush()
        except KeyboardInterrupt:
            ser.close()
            out.close()
            print("\n[stopped, %d bytes]" % total, flush=True)
            return 0
        except Exception as e:
            print("\n=== lost %s: %s (%d bytes so far) ===" % (port, e, total), flush=True)
            try:
                ser.close()
            except Exception:
                pass
            time.sleep(1.0)


if __name__ == "__main__":
    sys.exit(main())
