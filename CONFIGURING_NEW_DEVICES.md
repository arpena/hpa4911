# Configuring New HPA-4911 Devices

This guide walks you through setting up a BGH Smart Control Kit (HPA-4911) from factory state to fully working AC control, using the `hpa4911_config.py` standalone utility. No cloud account or mobile app required.

## Prerequisites

- Python 3.10+
- The HPA-4911 device (factory reset or new)
- A computer on the same local network. This shouldn't be the same server where Home Assistant and the integration are running, as they need to open the same UDP ports.
- Your AC remote control (for IR codec detection)

## Quick Start (TL;DR)

```bash
# 1. Connect to device AP, scan for WiFi networks
python3 hpa4911_config.py --ip 10.10.100.254 wifi-scan

# 2. Join it to your WiFi
python3 hpa4911_config.py --ip 10.10.100.254 join "MyWiFi" "mypassword"

# 3. Find device on your network (check router DHCP or scan)
python3 hpa4911_config.py scan

# 4. Detect your AC's IR codec
python3 hpa4911_config.py --ip <device_ip> detect-codec

# 5. Set the detected codec
python3 hpa4911_config.py --ip <device_ip> set-ir-codec <codec_name>

# 6. Test AC control
python3 hpa4911_config.py --ip <device_ip> ac cool --temp 24
```

## Step-by-Step Setup

### Step 1: Connect to the Device Access Point

When the HPA-4911 is in factory state (or after a factory reset), it creates a WiFi access point:

- SSID: `BGH-XXXX` (where XXXX varies per device)
- Network: `10.10.100.x`
- Device IP on AP: `10.10.100.254`

Connect your computer to this network.

If your device is not publishing the AP, or is in an unknown state, this is the procedure to perform a factory reset:

1. Unplug the AC and the mains powered device from the socket
2. Remove the battery cover of the IR device and press the recessed button once with a paper clip or SIM ejection tool. The IR LED will flash rapidly, but it is normally on the back side of the device that is adhered to the air conditioner, so it may be difficult to see
3. Remove a battery from the IR device and plug the mains powered device back in. Do not put the battery back in until "Step 4: Detect the IR Codec"
4. Press the button on the mains device for 5 seconds till it flashes red rapidly, and let it go
5. Press the button again for 10 seconds till it flashes green slowly
6. You should be able to join the AP from your computer.

### Step 2: Join the Device to Your WiFi

```bash
python3 hpa4911_config.py --ip 10.10.100.254 join "YourSSID" "YourPassword"
```

Options:
- `--security` — Security type: 0=Open, 3=WPA2 (default), 4=WPA3
- `--encryption` — Encryption type: 0=None, 3=AES (default)

After a successful join, the device reboots and connects to your WiFi network.

### Step 3: Find the Device on Your Network

Reconnect your computer to the same WiFi network and locate the device's new IP. You can:

**Option A: Scan from the utility**
```bash
python3 hpa4911_config.py scan --timeout 15
```

**Option B: Check your router's DHCP leases**

Look for a client with a MAC address starting with `AC:CF:23` (common for these devices).

### Step 4: Detect the IR Codec

The HPA-4911 needs to know which IR protocol your AC uses. Point your AC remote at the device and press the power button twice when prompted:

```bash
python3 hpa4911_config.py --ip <device_ip> detect-codec
```

The tool enters learning mode and waits for two IR signals. If both detections match, the codec is confirmed.

### Step 5: Set the IR Codec

Apply the detected codec to the device:

```bash
python3 hpa4911_config.py --ip <device_ip> set-ir-codec <codec_name>
```

Optional sensor mode (configures how the mains device detects AC compressor activity via vibration):
```bash
python3 hpa4911_config.py --ip <device_ip> set-ir-codec <codec_name> --sensor powered-by-ac
```

Sensor modes:
| Mode | Description |
|------|-------------|
| `none` | No vibration sensor (default) |
| `powered-by-ac` | Mains device powers the AC as a passthrough (direct vibration detection) |
| `near-ac` | Mains device plugged into a different socket than the AC (proximity vibration detection) |
| `external` | External sensor |

### Step 6: Test AC Control

```bash
# Turn on cooling at 24C
python3 hpa4911_config.py --ip <device_ip> ac cool --temp 24

# Turn off
python3 hpa4911_config.py --ip <device_ip> ac off

# Heat mode, low fan, 22C
python3 hpa4911_config.py --ip <device_ip> ac heat --temp 22 --fan low
```

### Step 7 (Optional): Redirect Cloud IP to Home Assistant

By default the device sends status updates to BGH's cloud server. You can redirect these to your Home Assistant instance so it receives push notifications from the device instead of relying solely on polling:

```bash
python3 hpa4911_config.py --ip <device_ip> set-cloud-ip <home_assistant_ip>
```

Replace `<home_assistant_ip>` with the local IP of your Home Assistant server (e.g., `192.168.1.50`). This causes the device to send periodic status packets directly to HA, which the integration listens for on UDP port 20911.

To verify the current setting:
```bash
python3 hpa4911_config.py --ip <device_ip> get-cloud-ip
```

> **Note:** This step is optional. The integration works without it via direct polling, but redirecting the cloud IP enables faster status updates and reduces latency.

### Step 8: Add to Home Assistant

Once the device responds to AC commands, add it via the Home Assistant UI:

1. Go to Settings > Devices & Services > Add Integration
2. Search for "Local BGH Smart"
3. Enter the device IP, MAC address, and a friendly name

---

## Available Commands

| Command | Description |
|---------|-------------|
| `scan` | Scan network for HPA-4911 devices |
| `join` | Join device to a WiFi network |
| `wifi-scan` | List WiFi networks visible to the device |
| `detect-codec` | Auto-detect IR codec from remote |
| `set-ir-codec` | Set IR protocol codec |
| `list-codecs` | List all supported IR codec names |
| `ac` | Send AC command (mode, fan, temp) |
| `monitor` | Monitor device status in real-time |
| `get-cloud-ip` | Get current cloud notification IP |
| `set-cloud-ip` | Redirect cloud notifications to custom IP |
| `set-temp-offset` | Calibrate room temperature reading |
| `calibrate` | Calibrate zero vibration sensor |
| `reboot` | Reboot device |
| `leave` | Factory reset (clears WiFi config) |

## Supported IR Codecs

| Codec Name | Code |
|------------|------|
| midea | 1 |
| samsung_short | 10 |
| samsung_mid | 12 |
| samsung_long | 13 |
| gree | 20 |
| delonghi | 30 |
| whitewestinghouse | 40 |
| tcl1 | 50 |
| tcl2 | 51 |
| lg | 60 |
| hisense | 70 |
| hisense_old | 71 |
| aux1 | 80 |
| aux2 | 81 |
| chigo | 90 |
| goodman | 100 |
| toshiba | 110 |
| carrier | 111 |
| rc5 | 120 |
| york | 130 |
| haier | 140 |
| mktech | 150 |

You can also list these with:
```bash
python3 hpa4911_config.py list-codecs
```

## AC Modes and Fan Speeds

**Modes:** `off`, `cool`, `heat`, `dry`, `fan`, `auto`

**Fan speeds:** `auto`, `low`, `mid`, `high`, `turbo`

## Monitoring

Watch device status and decoded IR commands in real-time:

```bash
python3 hpa4911_config.py --ip <device_ip> monitor
```

Press Ctrl+C to stop. Useful for verifying the device is receiving and decoding commands correctly.

## Advanced: Redirecting Cloud Notifications

You can redirect the device's cloud notification endpoint to a local server (or block it entirely):

```bash
# Check current cloud IP
python3 hpa4911_config.py --ip <device_ip> get-cloud-ip

# Redirect to a local address
python3 hpa4911_config.py --ip <device_ip> set-cloud-ip 192.168.1.100
```

## Troubleshooting

**No response from device**
- Verify you're on the same subnet
- Check that UDP ports 20910/20911 are not blocked by your firewall
- Try rebooting the device by power cycling it

**Codec not detected**
- Make sure you're pointing the remote directly at the HPA-4911 unit (not the AC)
- Press the power/on-off button specifically (other buttons may not trigger detection)
- Try increasing the timeout: `--timeout 60`

**AC not responding after codec set**
- Verify codec is correct by running `detect-codec` again
- Ensure line-of-sight between the HPA-4911 IR blaster and the AC unit
- Try a different codec variant (e.g., `samsung_short` vs `samsung_mid` vs `samsung_long`)

**MAC auto-detection fails**
- Specify the MAC manually: `--mac AC:CF:23:XX:XX:XX`
- Use the `scan` command to find the device MAC first

**Factory reset**
```bash
python3 hpa4911_config.py --ip <device_ip> leave
```
This clears WiFi configuration. You'll need to reconnect to the device AP and start from Step 1.
