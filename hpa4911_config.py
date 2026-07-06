#!/usr/bin/env python3
"""
HPA4911 Configuration Utility

Standalone tool for configuring BGH Smart Control Kit (HPA-4911) devices
without requiring the Solidmation cloud service or mobile app.

Communicates directly with the device over UDP (port 20910/20911) on the
local network using the Solidmation/Habeetat protocol.

Usage:
  python3 hpa4911_config.py --ip <device_ip> <command> [options]

  The --mac flag is optional; if omitted the tool auto-detects the device MAC
  by sending a probe packet.

Setup workflow (from factory reset to working AC control):
  1. Connect to the device AP (SSID "BGH-XXXX", network 10.10.100.x)
  2. Join the device to your WiFi:
       python3 hpa4911_config.py --ip 10.10.100.254 join <SSID> <password>
  3. Reconnect to your WiFi and find the device's new IP (check router DHCP)
  4. Detect IR codec (press AC remote button twice when prompted):
       python3 hpa4911_config.py --ip <device_ip> detect-codec
  5. Set IR codec:
       python3 hpa4911_config.py --ip <device_ip> set-ir-codec <codec_name>
  6. Control the AC:
       python3 hpa4911_config.py --ip <device_ip> ac cool --temp 24

Commands:
  get-cloud-ip     Get current cloud notification IP
  set-cloud-ip     Set cloud notification IP (redirect device to custom server)
  set-ir-codec     Set IR protocol codec and sensor mode
  detect-codec     Auto-detect IR codec (point AC remote at device)
  set-temp-offset  Set room temperature offset (calibration)
  calibrate        Calibrate zero vibration sensor
  reboot           Reboot device
  leave            Factory reset (WARNING: clears WiFi config)
  wifi-scan        Scan WiFi networks visible to device
  join             Join device to a WiFi network
  list-codecs      List available IR codec names
  ac               Send AC command (mode, fan, temperature)
  monitor          Monitor device status and IR commands in real-time

Protocol:
  Each UDP packet has a 17-byte header:
    [0]     Protocol version (0x00)
    [1:7]   Source MAC (6 bytes, zeros when sending from app/tool)
    [7:13]  Destination MAC (6 bytes)
    [13]    Sequence number
    [14]    Source endpoint
    [15]    Destination endpoint
    [16]    Command ID

  Key command IDs:
    97  (0x61) - HVAC SetMode (payload: mode, fan, flags, temp_lo, temp_hi)
    161 (0xa1) - Join (subcmds: 3=WiFi join, 7=get cloud IP, 8=set cloud IP, 9=enumerate)
    162 (0xa2) - CustomCommand (subcmds: 88=set codec, 90=learn mode, 92=get status, 101=temp offset)
    175 (0xaf) - Leave (factory reset)
    251 (0xfb) - Time sync (device → cloud)
    253 (0xfd) - Status report (device → cloud/app)
    255 (0xff) - Keep-alive

Supported IR codecs:
  midea(1) samsung_short(10) samsung_mid(12) samsung_long(13) gree(20)
  delonghi(30) whitewestinghouse(40) tcl1(50) tcl2(51) lg(60) hisense(70)
  hisense_old(71) aux1(80) aux2(81) chigo(90) goodman(100) toshiba(110)
  carrier(111) rc5(120) york(130) haier(140) mktech(150)

Sensor modes (for set-ir-codec --sensor):
  none(0)          - No vibration sensor (default)
  powered-by-ac(1) - Mains device powers the AC as a passthrough (direct vibration detection)
  near-ac(2)       - Mains device plugged into a different socket than the AC (proximity vibration)
  external(3)      - External sensor
"""

import argparse
import socket
import struct
import sys
import time

PORT_CLIENT = 20910
TIMEOUT = 5

# IR Protocol Codes (from CodecTypes.cs)
CODECS = {
    "midea": 1, "samsung_short": 10, "samsung_mid": 12, "samsung_long": 13,
    "gree": 20, "delonghi": 30, "whitewestinghouse": 40, "tcl1": 50,
    "tcl2": 51, "lg": 60, "hisense": 70, "hisense_old": 71, "aux1": 80,
    "aux2": 81, "chigo": 90, "goodman": 100, "toshiba": 110, "carrier": 111,
    "rc5": 120, "york": 130, "haier": 140, "mktech": 150,
}

SENSORS = {"none": 0, "powered-by-ac": 1, "near-ac": 2, "external": 3}


def mac_to_bytes(mac: str) -> bytes:
    return bytes.fromhex(mac.replace(":", "").replace("-", ""))


def build_header(dest_mac: bytes, command_id: int, seq: int = 1, dst_endpoint: int = 0) -> bytes:
    header = bytearray(17)
    header[0] = 0x00  # protocol version
    # bytes 1-6: source MAC (all zeros)
    header[7:13] = dest_mac
    header[13] = seq
    header[14] = 0  # source endpoint
    header[15] = dst_endpoint
    header[16] = command_id
    return bytes(header)


def send_and_wait_ack(sock: socket.socket, packet: bytes, target_ip: str) -> bool:
    sock.sendto(packet, (target_ip, PORT_CLIENT))
    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        try:
            sock.settimeout(deadline - time.time())
            data, addr = sock.recvfrom(1024)
            if len(data) >= 17 and data[16] == 128:  # Command_Rsp_ACK
                return True
        except socket.timeout:
            break
    return False


def get_cloud_ip(target_mac: str, target_ip: str) -> str | None:
    """Get the current cloud notification IP from the device (Command 161, SubCommand 7)."""
    mac_bytes = mac_to_bytes(target_mac)
    header = build_header(mac_bytes, 161)  # Command_Join
    packet = header + bytes([7])  # SubCommand_Get_Cloud_Notification_IP

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(TIMEOUT)
    try:
        sock.sendto(packet, (target_ip, PORT_CLIENT))
        while True:
            data, _ = sock.recvfrom(1024)
            if len(data) > 18 and data[16] == 161:
                # Skip header(17) + subcommand byte(1)
                ip_str = data[18:].decode("ascii", errors="ignore").split("\x00")[0]
                return ip_str
    except socket.timeout:
        return None
    finally:
        sock.close()


def detect_codec(target_mac: str, target_ip: str, timeout: int = 30) -> int | None:
    """Enable learning mode and wait for IR codec detection (CustomCommand 95 response)."""
    mac_bytes = mac_to_bytes(target_mac)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", 20911))
    sock.settimeout(timeout)
    try:
        # Enable learning mode (custom command 90, data=1)
        header = build_header(mac_bytes, 162)
        sock.sendto(header + bytes([90, 1]), (target_ip, PORT_CLIENT))

        # Wait for codec detection via debug messages (two presses)
        deadline = time.time() + timeout
        detections = []
        while time.time() < deadline and len(detections) < 2:
            try:
                sock.settimeout(deadline - time.time())
                data, addr = sock.recvfrom(1024)
                if len(data) > 17 and data[16] == 0xf5:
                    msg = data[17:].decode("ascii", errors="replace")
                    if "IRCodec_GetCodecForTimeArray" in msg:
                        start = msg.index("(") + 1
                        end = msg.index(")")
                        codec = int(msg[start:end])
                        detections.append(codec)
                        if len(detections) == 1:
                            print(f"  First press: codec {codec}. Press on/off again...")
            except socket.timeout:
                break
        if not detections:
            return None, None
        return detections[0], detections[1] if len(detections) > 1 else None
    finally:
        # Disable learning mode
        sock.sendto(header + bytes([90, 0]), (target_ip, PORT_CLIENT))
        sock.close()


def set_cloud_ip(target_mac: str, target_ip: str, new_cloud_ip: str) -> bool:
    """Set the cloud notification IP on the device (Command 161, SubCommand 8)."""
    mac_bytes = mac_to_bytes(target_mac)
    header = build_header(mac_bytes, 161)  # Command_Join
    # SubCommand 8 + IP padded to 16 bytes
    ip_bytes = new_cloud_ip.encode("ascii").ljust(16, b"\x00")[:16]
    packet = header + bytes([8]) + ip_bytes

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        return send_and_wait_ack(sock, packet, target_ip)
    finally:
        sock.close()


def set_ir_codec(target_mac: str, target_ip: str, codec: int, sensor: int = 0) -> bool:
    """Set IR protocol codec on the device (Command 162, CustomCommand 88)."""
    mac_bytes = mac_to_bytes(target_mac)
    header = build_header(mac_bytes, 162)  # Command_Custom_Command
    packet = header + bytes([88, codec, sensor])

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        return send_and_wait_ack(sock, packet, target_ip)
    finally:
        sock.close()


def set_temp_offset(target_mac: str, target_ip: str, offset: int) -> bool:
    """Set room temperature offset (Command 162, CustomCommand 101)."""
    mac_bytes = mac_to_bytes(target_mac)
    header = build_header(mac_bytes, 162)
    offset_bytes = struct.pack("<H", offset & 0xFFFF)
    packet = header + bytes([101]) + offset_bytes

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        return send_and_wait_ack(sock, packet, target_ip)
    finally:
        sock.close()


def calibrate_vibration(target_mac: str, target_ip: str) -> bool:
    """Calibrate zero vibration sensor (Command 162, CustomCommand 100)."""
    mac_bytes = mac_to_bytes(target_mac)
    header = build_header(mac_bytes, 162)
    packet = header + bytes([100])

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        return send_and_wait_ack(sock, packet, target_ip)
    finally:
        sock.close()


def leave(target_mac: str, target_ip: str) -> bool:
    """Factory reset device (Command 175). Device will lose WiFi config."""
    mac_bytes = mac_to_bytes(target_mac)
    header = build_header(mac_bytes, 175)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        # Send 4 times like the Android app does
        for i in range(4):
            sock.sendto(header, (target_ip, PORT_CLIENT))
        # Check for ACK
        sock.settimeout(TIMEOUT)
        try:
            data, _ = sock.recvfrom(1024)
            return len(data) >= 17 and data[16] == 128
        except socket.timeout:
            return True  # Device may have reset before responding
    finally:
        sock.close()


def reboot(target_mac: str, target_ip: str) -> bool:
    """Reboot device (Command 164)."""
    mac_bytes = mac_to_bytes(target_mac)
    header = build_header(mac_bytes, 164)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        return send_and_wait_ack(sock, header, target_ip)
    finally:
        sock.close()


def wifi_scan(target_mac: str, target_ip: str) -> list[dict]:
    """Scan for WiFi networks visible to the device (Command 161, SubCommand 5)."""
    mac_bytes = mac_to_bytes(target_mac)
    header = build_header(mac_bytes, 161)
    packet = header + bytes([5])

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(10)
    networks = []
    try:
        sock.sendto(packet, (target_ip, PORT_CLIENT))
        while True:
            data, _ = sock.recvfrom(1024)
            if len(data) > 18 and data[16] == 161 and data[17] == 6:
                ssid = data[18:50].decode("utf-8", errors="ignore").rstrip("\x00")
                sec = data[51]
                enc = data[52]
                rssi = data[53]
                if ssid:
                    networks.append({"ssid": ssid, "security": sec, "encryption": enc, "rssi": rssi})
            elif len(data) >= 17 and data[16] == 128:
                break  # ACK = scan complete
    except socket.timeout:
        pass
    finally:
        sock.close()
    return networks


def join_wifi(target_mac: str, target_ip: str, ssid: str, password: str,
              security: int = 3, encryption: int = 3) -> bool:
    """Join device to a WiFi network (Command 161, SubCommand 3).
    Security: 0=Open, 3=WPA2, 4=WPA3. Encryption: 0=None, 3=AES."""
    mac_bytes = mac_to_bytes(target_mac)
    header = build_header(mac_bytes, 161)

    # SSID padded to 32 bytes
    ssid_bytes = ssid.encode("utf-8").ljust(32, b"\x00")[:32]
    # Key padded to 33 bytes
    key_bytes = password.encode("utf-8").ljust(33, b"\x00")[:33]
    # Payload: SubCommand(3) + SSID(32) + Security(1) + Encryption(1) + Key(33)
    payload = bytes([3]) + ssid_bytes + bytes([security, encryption]) + key_bytes
    packet = header + payload

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        return send_and_wait_ack(sock, packet, target_ip)
    finally:
        sock.close()


def main():
    parser = argparse.ArgumentParser(description="HPA4911 Configuration Utility")
    parser.add_argument("--mac", help="Device MAC address (e.g. AC:CF:23:80:3D:9A). Auto-detected if omitted.")
    parser.add_argument("--ip", help="Device IP address")

    sub = parser.add_subparsers(dest="command", required=True)

    # Cloud IP
    sub.add_parser("get-cloud-ip", help="Get current cloud notification IP")
    p_cloud = sub.add_parser("set-cloud-ip", help="Set cloud notification IP")
    p_cloud.add_argument("cloud_ip", help="New cloud IP address")

    # IR codec
    p_codec = sub.add_parser("set-ir-codec", help="Set IR protocol codec")
    p_codec.add_argument("codec", choices=list(CODECS.keys()), help="IR codec name")
    p_codec.add_argument("--sensor", choices=list(SENSORS.keys()), default="none",
                         help="Configured sensor type (default: none)")

    # Monitor IR commands
    p_mon = sub.add_parser("monitor", help="Monitor device status and decoded IR commands")
    p_mon.add_argument("--timeout", type=int, default=0, help="Timeout in seconds (0=forever, default: 0)")

    # Detect codec
    p_detect = sub.add_parser("detect-codec", help="Detect IR codec (point AC remote at device and press a button)")
    p_detect.add_argument("--timeout", type=int, default=30, help="Timeout in seconds (default: 30)")

    # Temp offset
    p_offset = sub.add_parser("set-temp-offset", help="Set room temperature offset")
    p_offset.add_argument("offset", type=int, help="Offset value (signed int16)")

    # Calibrate
    sub.add_parser("calibrate", help="Calibrate zero vibration sensor")

    # Reboot
    sub.add_parser("reboot", help="Reboot device")

    # Leave (factory reset)
    sub.add_parser("leave", help="Factory reset device (WARNING: clears WiFi config)")

    # WiFi scan
    sub.add_parser("wifi-scan", help="Scan WiFi networks visible to device")

    # Join WiFi
    p_join = sub.add_parser("join", help="Join device to a WiFi network")
    p_join.add_argument("ssid", help="WiFi network name")
    p_join.add_argument("password", help="WiFi password")
    p_join.add_argument("--security", type=int, default=3, help="Security type (0=Open, 3=WPA2, 4=WPA3, default: 3)")
    p_join.add_argument("--encryption", type=int, default=3, help="Encryption type (0=None, 3=AES, default: 3)")

    # List codecs
    sub.add_parser("list-codecs", help="List available IR codecs")

    # Scan network
    p_scan = sub.add_parser("scan", help="Scan network for HPA4911 devices")
    p_scan.add_argument("--timeout", type=int, default=10, help="Scan duration in seconds (default: 10)")

    # AC control
    MODES = {"off": 0, "cool": 1, "heat": 2, "dry": 3, "fan": 4, "auto": 254}
    FANS = {"auto": 0, "low": 1, "mid": 2, "high": 3, "turbo": 4}
    p_ac = sub.add_parser("ac", help="Send AC command")
    p_ac.add_argument("mode", choices=list(MODES.keys()), help="AC mode")
    p_ac.add_argument("--temp", type=float, default=24.0, help="Target temperature (default: 24)")
    p_ac.add_argument("--fan", choices=list(FANS.keys()), default="auto", help="Fan speed (default: auto)")

    args = parser.parse_args()

    if args.command == "list-codecs":
        print("Available IR codecs:")
        for name, code in sorted(CODECS.items(), key=lambda x: x[1]):
            print(f"  {name:20s} = {code}")
        return

    if args.command == "scan":
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("0.0.0.0", 20911))
        sock.settimeout(1)
        # Send discovery probe (join enumerate) to broadcast
        probe = build_header(b'\xff\xff\xff\xff\xff\xff', 0xa1) + bytes([4])
        sock.sendto(probe, ("255.255.255.255", PORT_CLIENT))
        devices = {}
        print(f"Scanning for {args.timeout}s...")
        deadline = time.time() + args.timeout
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(2048)
                if len(data) >= 7:
                    mac_hex = data[1:7].hex()
                    if mac_hex == "000000000000" or mac_hex == "ffffffffffff":
                        continue
                    mac_str = ':'.join(mac_hex[i:i+2] for i in range(0, 12, 2)).upper()
                    if mac_str not in devices:
                        devices[mac_str] = addr[0]
                        print(f"  Found: {mac_str} at {addr[0]}")
            except socket.timeout:
                # Re-send probe periodically
                sock.sendto(probe, ("255.255.255.255", PORT_CLIENT))
                continue
        sock.close()
        if not devices:
            print("No devices found.")
        else:
            print(f"\n{len(devices)} device(s) found.")
        return

    mac = args.mac
    ip = args.ip

    if not ip:
        parser.error("--ip is required for this command")

    if not mac:
        # Auto-detect MAC by sending a keep-alive probe and reading response
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(TIMEOUT)
        # Send a packet with broadcast dst MAC to trigger a response
        probe = build_header(b'\xff\xff\xff\xff\xff\xff', 0xff)  # keep-alive
        try:
            sock.sendto(probe, (ip, PORT_CLIENT))
            data, addr = sock.recvfrom(1024)
            if len(data) >= 7 and addr[0] == ip:
                mac = data[1:7].hex()
                mac = ':'.join(mac[i:i+2] for i in range(0, 12, 2)).upper()
                print(f"Auto-detected MAC: {mac}")
        except socket.timeout:
            print("ERROR: Could not auto-detect MAC (no response from device)")
            sys.exit(1)
        finally:
            sock.close()

    if args.command == "get-cloud-ip":
        result = get_cloud_ip(mac, ip)
        if result:
            print(f"Current cloud IP: {result}")
        else:
            print("FAILED (no response)")
            sys.exit(1)
        return

    if args.command == "set-cloud-ip":
        ok = set_cloud_ip(mac, ip, args.cloud_ip)
        print(f"Set cloud IP to {args.cloud_ip}: {'OK' if ok else 'FAILED (no ACK)'}")

    elif args.command == "set-ir-codec":
        codec_val = CODECS[args.codec]
        sensor_val = SENSORS[args.sensor]
        ok = set_ir_codec(mac, ip, codec_val, sensor_val)
        print(f"Set IR codec to {args.codec} ({codec_val}), sensor={args.sensor}: {'OK' if ok else 'FAILED (no ACK)'}")

    elif args.command == "monitor":
        MODES = {0: "off", 1: "cool", 2: "heat", 3: "dry", 4: "fan", 254: "auto"}
        FANS = {0: "auto", 1: "low", 2: "mid", 3: "high", 4: "turbo", 254: "auto"}
        mac_bytes = mac_to_bytes(mac)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("0.0.0.0", 20911))
        if args.timeout:
            sock.settimeout(args.timeout)
        # Subscribe to status reports
        subscribe = build_header(mac_bytes, 161) + bytes([12])
        sock.sendto(subscribe, (ip, PORT_CLIENT))
        poll = build_header(b'\xff\xff\xff\xff\xff\xff', 228, dst_endpoint=1)
        sock.sendto(poll, (ip, PORT_CLIENT))
        print("Monitoring device... (Ctrl+C to stop)")
        try:
            while True:
                try:
                    data, addr = sock.recvfrom(2048)
                except socket.timeout:
                    break
                if len(data) < 17:
                    continue
                cmd = data[16]
                payload = data[17:]
                if cmd == 0xf5:  # Debug
                    msg = payload.decode("ascii", errors="replace")
                    print(f"  [DEBUG] {msg}")
                elif cmd == 0xf2:  # Status/config
                    if len(payload) >= 11:
                        mode = payload[1]
                        fan = payload[2]
                        flags = payload[3]
                        temp = int.from_bytes(payload[4:6], 'little', signed=True) / 100
                        setpoint = int.from_bytes(payload[6:8], 'little', signed=True) / 100
                        print(f"  [STATUS] mode={MODES.get(mode, mode)} fan={FANS.get(fan, fan)} temp={temp:.1f}C setpoint={setpoint:.1f}C flags=0x{flags:02x}")
                    else:
                        print(f"  [STATUS] {payload.hex()}")
                elif cmd == 0xfb:  # HA_TIME - time sync request
                    pass  # ignore time sync packets
                elif cmd == 0xfd:  # Full status
                    if len(payload) >= 12 and payload[0] == 6:
                        mode = payload[1]
                        fan = payload[2]
                        flags = payload[3]
                        temp = int.from_bytes(payload[4:6], 'little', signed=True) / 100
                        setpoint = int.from_bytes(payload[6:8], 'little', signed=True) / 100
                        print(f"  [HVAC] mode={MODES.get(mode, mode)} fan={FANS.get(fan, fan)} flags=0x{flags:02x} temp={temp:.1f}C setpoint={setpoint:.1f}C")
                    else:
                        print(f"  [FULL-STATUS] {payload.hex()}")
                elif cmd == 0xff:  # Ping
                    pass
                elif cmd == 0xa1:  # Join response
                    print(f"  [JOIN-RSP] subcmd={payload[0]}")
                else:
                    print(f"  [CMD 0x{cmd:02x}] {payload.hex()}")
        except KeyboardInterrupt:
            pass
        finally:
            sock.close()
        print("\nDone.")
        return

    elif args.command == "detect-codec":
        print(f"Learning mode enabled. Press on/off on your AC remote (twice to confirm)...")
        codec_names = {v: k for k, v in CODECS.items()}
        codec1, codec2 = detect_codec(mac, ip, args.timeout)
        if codec1 is not None:
            name = codec_names.get(codec1, "unknown")
            if codec2 is not None:
                if codec1 == codec2:
                    print(f"Confirmed codec: {name} ({codec1})")
                else:
                    name2 = codec_names.get(codec2, "unknown")
                    print(f"Mismatch! First: {name} ({codec1}), Second: {name2} ({codec2})")
                    print("  Try again with a single remote.")
            else:
                print(f"Detected codec: {name} ({codec1})")
                print("  (press again to confirm)")
        else:
            print("No codec detected (timeout)")
            sys.exit(1)
        return

    elif args.command == "set-temp-offset":
        ok = set_temp_offset(mac, ip, args.offset)
        print(f"Set temp offset to {args.offset}: {'OK' if ok else 'FAILED (no ACK)'}")

    elif args.command == "calibrate":
        ok = calibrate_vibration(mac, ip)
        print(f"Calibrate vibration: {'OK' if ok else 'FAILED (no ACK)'}")

    elif args.command == "reboot":
        ok = reboot(mac, ip)
        print(f"Reboot: {'OK' if ok else 'FAILED (no ACK)'}")

    elif args.command == "leave":
        print("WARNING: This will factory reset the device and clear WiFi config!")
        print("You will need to reconnect to the device AP and use 'join' to reconfigure.")
        confirm = input("Type YES to confirm: ")
        if confirm != "YES":
            print("Aborted.")
            sys.exit(0)
        ok = leave(mac, ip)
        print(f"Leave (factory reset): {'OK' if ok else 'FAILED'}")

    elif args.command == "wifi-scan":
        networks = wifi_scan(mac, ip)
        if networks:
            # Deduplicate by SSID, keep strongest signal
            seen = {}
            for n in networks:
                if n["ssid"] not in seen or n["rssi"] > seen[n["ssid"]]["rssi"]:
                    seen[n["ssid"]] = n
            print(f"{'SSID':<30} {'Sec':>3} {'Enc':>3} {'RSSI':>4}")
            print("-" * 44)
            for n in sorted(seen.values(), key=lambda x: x["rssi"], reverse=True):
                print(f"{n['ssid']:<30} {n['security']:>3} {n['encryption']:>3} {n['rssi']:>4}")
        else:
            print("No networks found")
            sys.exit(1)
        return

    elif args.command == "join":
        ok = join_wifi(mac, ip, args.ssid, args.password, args.security, args.encryption)
        print(f"Join WiFi '{args.ssid}': {'OK' if ok else 'FAILED (no ACK)'}")

    elif args.command == "ac":
        MODES = {"off": 0, "cool": 1, "heat": 2, "dry": 3, "fan": 4, "auto": 254}
        FANS = {"auto": 0, "low": 1, "mid": 2, "high": 3, "turbo": 4}
        mode = MODES[args.mode]
        fan = FANS[args.fan]
        temp_raw = int(args.temp * 100)
        temp_bytes = temp_raw.to_bytes(2, 'little', signed=True)
        mac_bytes = mac_to_bytes(mac)
        header = build_header(mac_bytes, 97, dst_endpoint=1)
        payload = bytes([mode, fan, 0]) + temp_bytes
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            ok = send_and_wait_ack(sock, header + payload, ip)
        finally:
            sock.close()
        print(f"AC {args.mode} fan={args.fan} temp={args.temp}: {'OK' if ok else 'FAILED (no ACK)'}")

    else:
        return

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
