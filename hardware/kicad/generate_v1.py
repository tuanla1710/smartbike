#!/usr/bin/env python3
"""Generate the Smart Bike Controller V1 KiCad schematic and PCB."""

import math
import shutil
import uuid
from pathlib import Path

KICAD = Path("/home/oran/opt/kicad-root/usr/share/kicad")
ROOT = Path("/home/oran/latuan/v5/hardware/kicad/smartbike_v5")
SYM = KICAD / "symbols"
FP = KICAD / "footprints"

NS = uuid.UUID("6f0b9a1e-4c2d-4a7e-9b11-0a5d8e3c7f21")


def uid(name):
    return str(uuid.uuid5(NS, name))


def fmt(v):
    s = f"{float(v):.4f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


class Part:
    def __init__(self, ref, lib_id, value, footprint, pinmap, sheet, group, dnp=False):
        self.ref = ref
        self.lib_id = lib_id
        self.value = value
        self.footprint = footprint
        self.pinmap = pinmap
        self.sheet = sheet
        self.group = group
        self.dnp = dnp
        self.pins = {}
        self.sx = 0.0
        self.sy = 0.0


def parse_sexp(text):
    s = text
    i = 0
    n = len(s)

    def rec():
        nonlocal i
        while i < n and s[i].isspace():
            i += 1
        if i >= n:
            raise ValueError("unexpected eof")
        if s[i] == "(":
            i += 1
            items = []
            while True:
                while i < n and s[i].isspace():
                    i += 1
                if i < n and s[i] == ")":
                    i += 1
                    return items
                items.append(rec())
        if s[i] == '"':
            i += 1
            buf = []
            while i < n:
                if s[i] == "\\":
                    i += 1
                    buf.append(s[i])
                    i += 1
                    continue
                if s[i] == '"':
                    i += 1
                    break
                buf.append(s[i])
                i += 1
            return "".join(buf)
        start = i
        while i < n and (not s[i].isspace()) and s[i] not in "()":
            i += 1
        return s[start:i]

    return rec()


def extract_symbol(text, name):
    key = f'(symbol "{name}"'
    i = text.find(key)
    if i < 0:
        raise KeyError(name)
    # The closing quote is part of key, so a longer name such as NAME_1_1 does not match.
    depth = 0
    in_str = False
    j = i
    while j < len(text):
        c = text[j]
        if in_str:
            if c == "\\":
                j += 2
                continue
            if c == '"':
                in_str = False
            j += 1
            continue
        if c == '"':
            in_str = True
            j += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[i : j + 1]
        j += 1
    raise ValueError(f"unclosed symbol {name}")


class LibCache:
    def __init__(self):
        self.files = {}
        self.trees = {}

    def text(self, filename):
        if filename not in self.files:
            self.files[filename] = (SYM / filename).read_text(errors="replace")
        return self.files[filename]

    def symbols(self, filename):
        if filename not in self.trees:
            tree = parse_sexp(self.text(filename))
            self.trees[filename] = {
                node[1]: node
                for node in tree[1:]
                if isinstance(node, list) and node and node[0] == "symbol"
            }
        return self.trees[filename]

    def resolved_pins(self, filename, name):
        syms = self.symbols(filename)
        sym = syms[name]
        parent = sym
        for child in sym:
            if isinstance(child, list) and child and child[0] == "extends":
                parent = syms[child[1]]
                break
        pins = []

        def walk(node):
            if isinstance(node, list) and node and node[0] == "pin":
                num = pname = None
                at = (0.0, 0.0, 0.0)
                for c in node:
                    if isinstance(c, list) and c and c[0] == "name":
                        pname = c[1]
                    elif isinstance(c, list) and c and c[0] == "number":
                        num = str(c[1])
                    elif isinstance(c, list) and c and c[0] == "at":
                        at = (float(c[1]), float(c[2]), float(c[3]))
                pins.append((num, pname, node[1], at))
            elif isinstance(node, list):
                for c in node:
                    walk(c)

        walk(parent)
        return pins

    def embed_blocks(self, lib_id):
        lib, name = lib_id.split(":")
        filename = f"{lib}.kicad_sym"
        raw = extract_symbol(self.text(filename), name)
        syms = self.symbols(filename)
        extends = None
        for child in syms[name]:
            if isinstance(child, list) and child and child[0] == "extends":
                extends = child[1]
                break
        if extends:
            # KiCad 9 rejects an embedded symbol that uses extends, even when the
            # parent is embedded beside it. Paste the parent body under the
            # derived symbol's name. Pinout is inherited, so this is equivalent.
            raw = extract_symbol(self.text(filename), extends)
            raw = raw.replace(f'(symbol "{extends}"', f'(symbol "{lib_id}"', 1)
            raw = raw.replace(f'(symbol "{extends}_', f'(symbol "{name}_')
            return [raw]
        raw = raw.replace(f'(symbol "{name}"', f'(symbol "{lib_id}"', 1)
        return [raw]


LIBS = LibCache()


def resolve(part):
    lib, name = part.lib_id.split(":")
    pins = LIBS.resolved_pins(f"{lib}.kicad_sym", name)
    by_name = {}
    for num, pname, typ, at in pins:
        by_name.setdefault(pname, []).append(num)
    assigned = {num: None for num, pname, typ, at in pins}
    for key, net in part.pinmap.items():
        if key.startswith("#"):
            num = key[1:]
            if num not in assigned:
                raise SystemExit(f"{part.ref}: pin {num} not on {part.lib_id}")
            assigned[num] = net
        elif key in by_name:
            for num in by_name[key]:
                assigned[num] = net
        elif key in assigned:
            assigned[key] = net
        else:
            raise SystemExit(f"{part.ref}: pin {key} not on {part.lib_id} ({sorted(by_name)})")
    part.pins = assigned
    part.pin_geom = {num: (at, typ) for num, pname, typ, at in pins}
    return part


R0603 = "Resistor_SMD:R_0603_1608Metric"
R0402 = "Resistor_SMD:R_0402_1005Metric"
R2512 = "Resistor_SMD:R_2512_6332Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
DSMA = "Diode_SMD:D_SMA"
DSMC = "Diode_SMD:D_SMC"
DSOD = "Diode_SMD:D_SOD-123"
SOT23 = "Package_TO_SOT_SMD:SOT-23"
NMOS = "Transistor_FET:Q_NMOS_GSD"
PMOS = "Transistor_FET:Q_PMOS_GSD"


def R(ref, value, footprint, a, b, sheet, group, dnp=False):
    return Part(ref, "Device:R", value, footprint, {"1": a, "2": b}, sheet, group, dnp)


def C(ref, value, footprint, a, b, sheet, group, dnp=False):
    return Part(ref, "Device:C", value, footprint, {"1": a, "2": b}, sheet, group, dnp)


def diode(ref, value, footprint, cathode, anode, sheet, group, lib="Device:D_Schottky"):
    return Part(ref, lib, value, footprint, {"1": cathode, "2": anode}, sheet, group)


def nmos(ref, value, footprint, gate, drain, source, sheet, group, dnp=False):
    return Part(ref, NMOS, value, footprint, {"1": gate, "3": drain, "2": source}, sheet, group, dnp)


def build_parts():
    p = []
    # Power
    p += [
        Part("J1", "Connector:Conn_01x02_Pin", "POWER", "Connector_JST:JST_XH_B2B-XH-AM_1x02_P2.50mm_Vertical",
             {"Pin_1": "+5V_IN", "Pin_2": "GND"}, "power", "conn"),
        Part("F1", "Device:Fuse", "3A", "Fuse:Fuse_1206_3216Metric", {"1": "+5V_IN", "2": "+5V_FUSED"}, "power", "power"),
        Part("Q1", PMOS, "DMG2305UX", SOT23, {"1": "Q1_GATE", "2": "+5V_FUSED", "3": "+5V_PROT"}, "power", "power"),
        R("R1", "100k", R0603, "Q1_GATE", "GND", "power", "power"),
        diode("D1", "BZT52C5V6", DSOD, "+5V_FUSED", "Q1_GATE", "power", "power", "Device:D_Zener"),
        diode("D2", "SMAJ5.0A", DSMA, "+5V_PROT", "GND", "power", "power", "Device:D"),
        diode("D3", "SS54", DSMC, "+5V_MERGED", "+5V_PROT", "power", "power"),
        Part("F2", "Device:Fuse", "1.1A", "Fuse:Fuse_1812_4532Metric", {"1": "USB_VBUS", "2": "USB_VBUS_FUSED"}, "power", "power"),
        diode("D4", "SS34", DSMA, "+5V_MERGED", "USB_VBUS_FUSED", "power", "power"),
        R("R2", "10m", R2512, "+5V_MERGED", "+5V_SYS", "power", "power"),
        C("C2", "22uF", C0805, "+5V_SYS", "GND", "power", "power"),
        Part("U1", "smartbike:INA228", "INA228", "Package_SO:VSSOP-10_3x3mm_P0.5mm", {
            "Vbus": "+5V_SYS", "Vin+": "+5V_MERGED", "Vin-": "+5V_SYS", "VS": "+3V3", "GND": "GND",
            "A1": "GND", "A0": "GND", "SDA": "I2C_SDA", "SCL": "I2C_SCL", "~{Alert}": "ALERT",
        }, "power", "power"),
        C("C1", "100nF", C0402, "+3V3", "GND", "power", "power"),
        R("R3", "10k", R0603, "ALERT", "+3V3", "power", "power"),
        Part("U2", "smartbike:TPS62162DSG", "TPS62162-Q1",
             "Package_SON:WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm_ThermalVias", {
                 "VIN": "+5V_SYS", "EN": "+5V_SYS", "PG": "PGOOD", "PAD": "GND", "PGND": "GND",
                 "AGND": "GND", "SW": "SW", "VOS": "+3V3", "FB": "GND",
             }, "power", "power"),
        Part("L1", "Device:L", "2.2uH", "Inductor_SMD:L_1210_3225Metric", {"1": "SW", "2": "+3V3"}, "power", "power"),
        C("C3", "10uF", C0805, "+5V_SYS", "GND", "power", "power"),
        C("C4", "100nF", C0402, "+5V_SYS", "GND", "power", "power"),
        C("C5", "22uF", C0805, "+3V3", "GND", "power", "power"),
        R("R4", "100k", R0603, "PGOOD", "+3V3", "power", "power"),
    ]
    # USB
    p += [
        Part("J8", "Connector:USB_C_Receptacle_USB2.0_16P", "USB-C",
             "Connector_USB:USB_C_Receptacle_HCTL_HC-TYPE-C-16P-01A", {
                 "VBUS": "USB_VBUS", "GND": "GND", "SHIELD": "GND", "CC1": "CC1", "CC2": "CC2",
                 "D+": "USB_D_P_CONN", "D-": "USB_D_N_CONN",
             }, "usb", "usb"),
        R("R5", "5.1k", R0603, "CC1", "GND", "usb", "usb"),
        R("R6", "5.1k", R0603, "CC2", "GND", "usb", "usb"),
        Part("U3", "smartbike:USBLC6-2SC6", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6", {
            "#1": "USB_D_P_CONN", "#6": "USB_D_P_ESD", "#3": "USB_D_N_CONN", "#4": "USB_D_N_ESD",
            "#5": "USB_VBUS", "#2": "GND",
        }, "usb", "usb"),
        C("C6", "100nF", C0402, "USB_VBUS", "GND", "usb", "usb"),
        R("R7", "22", R0402, "USB_D_P_ESD", "USB_D_P", "usb", "usb"),
        R("R8", "22", R0402, "USB_D_N_ESD", "USB_D_N", "usb", "usb"),
        C("C7", "DNP", C0402, "USB_D_P", "GND", "usb", "usb", dnp=True),
        C("C8", "DNP", C0402, "USB_D_N", "GND", "usb", "usb", dnp=True),
    ]
    # MCU
    esp = {f"IO{n}": None for n in []}
    esp_map = {
        "3V3": "+3V3", "GND": "GND", "EN": "EN", "IO0": "BOOT",
        "IO4": "LIDAR_XSHUT", "IO5": "LIDAR_INT", "IO6": "HORN_GATE", "IO7": "HEADLIGHT_GATE",
        "IO8": "I2C_SDA", "IO9": "I2C_SCL", "IO10": "LEFT_GATE", "IO11": "RIGHT_GATE",
        "IO12": "TAIL_GATE", "IO13": "BRAKE_GATE", "IO15": "LEFT_SW", "IO16": "RIGHT_SW",
        "IO17": "GPS_TXD", "IO18": "GPS_RXD", "USB_D-": "USB_D_N", "USB_D+": "USB_D_P",
        "IO21": "HORN_SW", "IO38": "IMU_INT", "IO39": "LIGHT_SW", "IO40": "BRAKE_SW",
        "IO41": "AUX_GATE", "IO42": "STATUS_LED",
    }
    p += [
        Part("U4", "RF_Module:ESP32-S3-WROOM-1", "ESP32-S3-WROOM-1-N8", "smartbike:ESP32-S3-WROOM-1", esp_map, "mcu", "mcu"),
        C("C9", "10uF", C0603, "+3V3", "GND", "mcu", "mcu"),
        C("C10", "100nF", C0402, "+3V3", "GND", "mcu", "mcu"),
        R("R9", "10k", R0603, "EN", "+3V3", "mcu", "mcu"),
        C("C11", "1uF", C0402, "EN", "GND", "mcu", "mcu"),
        Part("SW1", "Switch:SW_Push", "RESET", "Button_Switch_THT:SW_PUSH_6mm", {"1": "EN", "2": "GND"}, "mcu", "mcu"),
        R("R10", "10k", R0603, "BOOT", "+3V3", "mcu", "mcu"),
        Part("SW2", "Switch:SW_Push", "BOOT", "Button_Switch_THT:SW_PUSH_6mm", {"1": "BOOT", "2": "GND"}, "mcu", "mcu"),
        R("R11", "330", R0603, "STATUS_LED", "STATUS_LED_A", "mcu", "mcu"),
        diode("D5", "GREEN", "LED_SMD:LED_0603_1608Metric", "GND", "STATUS_LED_A", "mcu", "mcu", "Device:LED"),
    ]
    # Sensors
    p += [
        R("R13", "4.7k", R0603, "I2C_SDA", "+3V3", "sensors", "sensors"),
        R("R14", "4.7k", R0603, "I2C_SCL", "+3V3", "sensors", "sensors"),
        Part("U5", "smartbike:BMI270", "BMI270", "Package_LGA:Bosch_LGA-14_3x2.5mm_P0.5mm", {
            "SDO": "GND", "SDx": "I2C_SDA", "SCx": "I2C_SCL", "CSB": "+3V3", "INT1": "IMU_INT",
            "VDDIO": "+3V3", "GNDIO": "GND", "VDD": "+3V3", "GND": "GND",
        }, "sensors", "sensors"),
        C("C13", "100nF", C0402, "+3V3", "GND", "sensors", "sensors"),
        C("C14", "100nF", C0402, "+3V3", "GND", "sensors", "sensors"),
        Part("U6", "smartbike:BH1750FVI", "BH1750FVI", "smartbike:BH1750FVI_WSOF6", {
            "VCC": "+3V3", "ADDR": "GND", "GND": "GND", "SDA": "I2C_SDA", "DVI": "DVI", "SCL": "I2C_SCL",
        }, "sensors", "sensors"),
        C("C15", "100nF", C0402, "+3V3", "GND", "sensors", "sensors"),
        R("R12", "10k", R0603, "+3V3", "DVI", "sensors", "sensors"),
        C("C16", "100nF", C0402, "DVI", "GND", "sensors", "sensors"),
        Part("MOD1", "Connector:Conn_01x06_Pin", "VL53L1X", "Connector_JST:JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical", {
            "Pin_1": "+3V3", "Pin_2": "GND", "Pin_3": "I2C_SDA", "Pin_4": "I2C_SCL",
            "Pin_5": "LIDAR_XSHUT", "Pin_6": "LIDAR_INT",
        }, "sensors", "lidar"),
        R("R15", "10k", R0603, "LIDAR_XSHUT", "+3V3", "sensors", "sensors"),
        R("R16", "10k", R0603, "LIDAR_INT", "+3V3", "sensors", "sensors"),
        C("C17", "100nF", C0402, "+3V3", "GND", "sensors", "sensors"),
    ]
    # GPS
    p += [
        Part("U7", "RF_GPS:MAX-M10S", "MAX-M10S", "RF_GPS:ublox_MAX", {
            "TXD": "GPS_TXD", "RXD": "GPS_RXD", "VCC": "+3V3", "VCC_IO": "+3V3", "V_BCKP": "+3V3",
            "GND": "GND", "RF_IN": "GPS_RF",
        }, "gps", "gps"),
        C("C18", "1uF", C0402, "+3V3", "GND", "gps", "gps"),
        C("C19", "100nF", C0402, "+3V3", "GND", "gps", "gps"),
        Part("AE1", "Device:Antenna_Chip", "GPS_L1", "RF_Antenna:Pulse_W3011", {"FEED": "GPS_RF", "PCB_Trace": "GND"}, "gps", "antenna"),
        R("R17", "0R", R0402, "GPS_RF", "GPS_RF_ANT", "gps", "gps"),
        C("C20", "DNP", C0402, "GPS_RF_ANT", "GND", "gps", "gps", dnp=True),
        C("C21", "DNP", C0402, "GPS_RF", "GND", "gps", "gps", dnp=True),
    ]
    # The antenna feed is pin FEED. R17 sits in series, so FEED net must be the module side
    # only if we insert the resistor. Reconnect AE1 feed to the antenna side.
    for part in p:
        if part.ref == "AE1":
            part.pinmap["FEED"] = "GPS_RF_ANT"
    # Outputs
    channels = [
        ("Q2", "Si2302CDS", "HEADLIGHT_GATE", "HEADLIGHT_N", "R18", "R25", "D6", "SS14", DSMA),
        ("Q3", "Si2302CDS", "TAIL_GATE", "TAIL_N", "R19", "R26", "D7", "SS14", DSMA),
        ("Q4", "Si2302CDS", "BRAKE_GATE", "BRAKE_N", "R20", "R27", "D8", "SS14", DSMA),
        ("Q5", "Si2302CDS", "LEFT_GATE", "LEFT_N", "R21", "R28", "D9", "SS14", DSMA),
        ("Q6", "Si2302CDS", "RIGHT_GATE", "RIGHT_N", "R22", "R29", "D10", "SS14", DSMA),
        ("Q7", "Si2302CDS", "AUX_GATE", "AUX_N", "R23", "R30", "D11", "SS14", DSMA),
    ]
    for ref, val, gate, drain, rs, rg, dref, dval, dfp in channels:
        p.append(nmos(ref, val, SOT23, gate, drain, "GND", "outputs", "fet"))
        p.append(R(rs, "100", R0603, gate, gate + "_G", "outputs", "fet"))
        p.append(R(rg, "100k", R0603, gate + "_G", "GND", "outputs", "fet"))
        p.append(diode(dref, dval, dfp, "+5V_SYS", drain, "outputs", "fet"))
    # Gate nets in the table above are the GPIO nets. Series resistor must sit between GPIO and gate.
    # Fix: GPIO -- series -- gate node, pulldown on gate node. I used gate as both ends.
    # Rebuild those six channels cleanly below by replacing the mistaken nets.
    p = [part for part in p if part.sheet != "outputs"]
    channels = [
        ("Q2", "HEADLIGHT_GATE", "HEADLIGHT_G", "HEADLIGHT_N", "R18", "R25", "D6"),
        ("Q3", "TAIL_GATE", "TAIL_G", "TAIL_N", "R19", "R26", "D7"),
        ("Q4", "BRAKE_GATE", "BRAKE_G", "BRAKE_N", "R20", "R27", "D8"),
        ("Q5", "LEFT_GATE", "LEFT_G", "LEFT_N", "R21", "R28", "D9"),
        ("Q6", "RIGHT_GATE", "RIGHT_G", "RIGHT_N", "R22", "R29", "D10"),
        ("Q7", "AUX_GATE", "AUX_G", "AUX_N", "R23", "R30", "D11"),
    ]
    for q, gpio, gate, drain, rs, rg, dref in channels:
        p.append(nmos(q, "Si2302CDS", SOT23, gate, drain, "GND", "outputs", "fet"))
        p.append(R(rs, "100", R0603, gpio, gate, "outputs", "fet"))
        p.append(R(rg, "100k", R0603, gate, "GND", "outputs", "fet"))
        p.append(diode(dref, "SS14", DSMA, "+5V_SYS", drain, "outputs", "fet"))
    p += [
        nmos("Q8A", "Si2302CDS", SOT23, "HORN_G", "HORN_N", "GND", "outputs", "fet", dnp=True),
        nmos("Q8B", "DNP-DPAK", "smartbike:TO-252-2_GSD", "HORN_G", "HORN_N", "GND", "outputs", "fet", dnp=True),
        R("R24", "100", R0603, "HORN_GATE", "HORN_G", "outputs", "fet"),
        R("R31", "100k", R0603, "HORN_G", "GND", "outputs", "fet"),
        diode("D12", "SS34", DSMA, "+5V_SYS", "HORN_N", "outputs", "fet"),
        Part("J3", "Connector:Conn_01x02_Pin", "HEADLIGHT", "Connector_JST:JST_XH_B2B-XH-AM_1x02_P2.50mm_Vertical",
             {"Pin_1": "+5V_SYS", "Pin_2": "HEADLIGHT_N"}, "outputs", "conn"),
        Part("J4", "Connector:Conn_01x03_Pin", "REAR", "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical",
             {"Pin_1": "+5V_SYS", "Pin_2": "TAIL_N", "Pin_3": "BRAKE_N"}, "outputs", "conn"),
        Part("J5", "Connector:Conn_01x03_Pin", "TURN", "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical",
             {"Pin_1": "+5V_SYS", "Pin_2": "LEFT_N", "Pin_3": "RIGHT_N"}, "outputs", "conn"),
        Part("J6", "Connector:Conn_01x02_Pin", "HORN", "Connector_JST:JST_XH_B2B-XH-AM_1x02_P2.50mm_Vertical",
             {"Pin_1": "+5V_SYS", "Pin_2": "HORN_N"}, "outputs", "conn"),
        Part("J7", "Connector:Conn_01x02_Pin", "AUX", "Connector_JST:JST_XH_B2B-XH-AM_1x02_P2.50mm_Vertical",
             {"Pin_1": "+5V_SYS", "Pin_2": "AUX_N"}, "outputs", "conn"),
    ]
    # Handlebar
    switches = [
        ("LEFT_SW", "R32", "C22"),
        ("RIGHT_SW", "R33", "C23"),
        ("HORN_SW", "R34", "C24"),
        ("LIGHT_SW", "R35", "C25"),
        ("BRAKE_SW", "R36", "C26"),
        ("HAZARD_SW", "R37", "C27"),
    ]
    for net, rr, cc in switches:
        p.append(R(rr, "10k", R0603, net, "+3V3", "handlebar", "logic"))
        p.append(C(cc, "100nF", C0402, net, "GND", "handlebar", "logic"))
    p += [
        Part("J2", "Connector:Conn_01x08_Pin", "HANDLEBAR", "Connector_JST:JST_XH_B8B-XH-A_1x08_P2.50mm_Vertical", {
            "Pin_1": "+3V3", "Pin_2": "GND", "Pin_3": "LEFT_SW", "Pin_4": "RIGHT_SW",
            "Pin_5": "HORN_SW", "Pin_6": "LIGHT_SW", "Pin_7": "HAZARD_SW", "Pin_8": "BRAKE_SW",
        }, "handlebar", "conn"),
        diode("D13", "BAT54", DSOD, "HAZARD_SW", "LEFT_SW", "handlebar", "logic"),
        diode("D14", "BAT54", DSOD, "HAZARD_SW", "RIGHT_SW", "handlebar", "logic"),
    ]
    # Test points
    tps = [
        ("TP1", "+5V_IN"), ("TP2", "+5V_SYS"), ("TP3", "+3V3"), ("TP4", "GND"),
        ("TP5", "USB_D_P"), ("TP6", "USB_D_N"), ("TP7", "GPS_TXD"), ("TP8", "GPS_RXD"),
        ("TP9", "I2C_SDA"), ("TP10", "I2C_SCL"), ("TP11", "HEADLIGHT_GATE"),
        ("TP12", "HORN_GATE"), ("TP13", "LEFT_GATE"), ("TP14", "RIGHT_GATE"),
    ]
    for ref, net in tps:
        sheet = "power" if net in ("+5V_IN", "+5V_SYS", "+3V3", "GND") else "mcu"
        if net.startswith("GPS"):
            sheet = "gps"
        if net.startswith("I2C"):
            sheet = "sensors"
        if net.endswith("GATE"):
            sheet = "outputs"
        if net.startswith("USB"):
            sheet = "usb"
        p.append(Part(ref, "Connector:TestPoint", ref, "TestPoint:TestPoint_Pad_D1.5mm", {"1": net}, sheet, "tp"))
    for part in p:
        resolve(part)
    add_power_flags(p)
    return p


def add_power_flags(parts):
    types = {}
    for part in parts:
        for num, net in part.pins.items():
            if not net:
                continue
            typ = part.pin_geom[num][1]
            types.setdefault(net, set()).add(typ)
    n = 1
    for net, typset in sorted(types.items()):
        if "power_in" in typset and "power_out" not in typset:
            flag = Part(f"#PF{n}", "power:PWR_FLAG", "PWR_FLAG", "", {"1": net}, "power", "flag")
            flag.bom = False
            resolve(flag)
            parts.append(flag)
            n += 1


def effects(size=1.27, hide=False, justify=None):
    just = f"\n\t\t\t(justify {justify})" if justify else ""
    hide_s = "\n\t\t\t(hide yes)" if hide else ""
    return f"""(effects
\t\t\t(font
\t\t\t\t(size {fmt(size)} {fmt(size)})
\t\t\t){just}{hide_s}
\t\t)"""


def pack_sheet(parts):
    # 1.27 mm is KiCad's 50 mil connection grid. Symbol origins stay on that grid
    # so pin tips (already on-grid in the libraries) stay on-grid too.
    grid = 1.27
    x = 32 * grid
    y = 32 * grid
    row_h = 0.0
    limit = 800 * grid
    for part in parts:
        xs = [at[0] for at, typ in part.pin_geom.values()]
        ys = [at[1] for at, typ in part.pin_geom.values()]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        # Outward 7.62 mm wire plus a gap, both multiples of the grid.
        w = (maxx - minx) + 16 * grid
        h = (maxy - miny) + 16 * grid
        if x + w > limit:
            x = 32 * grid
            y += row_h + 4 * grid
            row_h = 0.0
        part.sx = x - minx + 6 * grid
        part.sy = y - miny + 6 * grid
        x += w + 4 * grid
        row_h = max(row_h, h)
    return y + row_h + 24 * grid


def emit_part(part, sheet_uuid, root_uuid):
    geom_wires = []
    labels = []
    ncs = []
    pin_lines = []
    for num, net in part.pins.items():
        (px, py, ang), typ = part.pin_geom[num]
        # Symbol libraries are Y-up. A schematic sheet is Y-down, so KiCad
        # negates the pin Y when the symbol is placed.
        x = part.sx + px
        y = part.sy - py
        pin_lines.append(f'\t\t(pin "{num}"\n\t\t\t(uuid "{uid(part.ref + ":" + num)}")\n\t\t)')
        if net is None:
            ncs.append(f'\t(no_connect\n\t\t(at {fmt(x)} {fmt(y)})\n\t\t(uuid "{uid("nc:" + part.ref + ":" + num)}")\n\t)')
            continue
        # Library pin angle points from the tip back into the body. Flip it
        # into sheet coordinates and step outward, away from the body.
        out = (180 - ang) % 360
        rad = math.radians(out)
        x2 = x + math.cos(rad) * 7.62
        y2 = y + math.sin(rad) * 7.62
        geom_wires.append(
            f'\t(wire\n\t\t(pts\n\t\t\t(xy {fmt(x)} {fmt(y)}) (xy {fmt(x2)} {fmt(y2)})\n\t\t)\n'
            f'\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n'
            f'\t\t(uuid "{uid("w:" + part.ref + ":" + num)}")\n\t)'
        )
        labels.append(
            f'\t(global_label "{net}"\n\t\t(shape passive)\n\t\t(at {fmt(x2)} {fmt(y2)} {fmt(out)})\n'
            f'\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n\t\t)\n'
            f'\t\t(uuid "{uid("gl:" + part.ref + ":" + num)}")\n'
            f'\t\t(property "Intersheetrefs" "${{INTERSHEET_REFS}}"\n'
            f'\t\t\t(at {fmt(x2)} {fmt(y2)} 0)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n'
            f'\t\t\t\t(hide yes)\n\t\t\t)\n\t\t)\n\t)'
        )
    xs = [at[0] for at, typ in part.pin_geom.values()]
    ys = [at[1] for at, typ in part.pin_geom.values()]
    ref_y = part.sy + max(ys) + 2.54
    val_y = ref_y + 2.54
    dnp = "yes" if part.dnp else "no"
    bom = "no" if part.lib_id == "power:PWR_FLAG" else "yes"
    board = "no" if part.lib_id == "power:PWR_FLAG" else "yes"
    path = f"/{root_uuid}/{sheet_uuid}"
    body = f'''\t(symbol
\t\t(lib_id "{part.lib_id}")
\t\t(at {fmt(part.sx)} {fmt(part.sy)} 0)
\t\t(unit 1)
\t\t(exclude_from_sim no)
\t\t(in_bom {bom})
\t\t(on_board {board})
\t\t(dnp {dnp})
\t\t(uuid "{uid("sym:" + part.ref)}")
\t\t(property "Reference" "{part.ref}"
\t\t\t(at {fmt(part.sx)} {fmt(ref_y)} 0)
\t\t\t{effects()}
\t\t)
\t\t(property "Value" "{part.value}"
\t\t\t(at {fmt(part.sx)} {fmt(val_y)} 0)
\t\t\t{effects()}
\t\t)
\t\t(property "Footprint" "{part.footprint}"
\t\t\t(at {fmt(part.sx)} {fmt(part.sy)} 0)
\t\t\t{effects(hide=True)}
\t\t)
\t\t(property "Datasheet" "~"
\t\t\t(at {fmt(part.sx)} {fmt(part.sy)} 0)
\t\t\t{effects(hide=True)}
\t\t)
{chr(10).join(pin_lines)}
\t\t(instances
\t\t\t(project "smartbike_v5"
\t\t\t\t(path "{path}"
\t\t\t\t\t(reference "{part.ref}")
\t\t\t\t\t(unit 1)
\t\t\t\t)
\t\t\t)
\t\t)
\t)'''
    return body, geom_wires, labels, ncs


def write_sheet(path, title, parts, root_uuid, sheet_uuid, page):
    blocks = []
    seen = set()
    for part in parts:
        for block in LIBS.embed_blocks(part.lib_id):
            first = block.split("\n", 1)[0]
            if first not in seen:
                seen.add(first)
                blocks.append(block)
    bodies = []
    wires = []
    labels = []
    ncs = []
    for part in parts:
        body, w, lab, nc = emit_part(part, sheet_uuid, root_uuid)
        bodies.append(body)
        wires.extend(w)
        labels.extend(lab)
        ncs.extend(nc)
    text = f'''(kicad_sch
\t(version 20250114)
\t(generator "smartbike_v1")
\t(generator_version "9.0")
\t(uuid "{sheet_uuid}")
\t(paper "A0")
\t(title_block
\t\t(title "{title}")
\t\t(date "2026-10-07")
\t\t(rev "V1")
\t\t(company "Smart Bike V5")
\t)
\t(lib_symbols
{chr(10).join(blocks)}
\t)
{chr(10).join(bodies)}
{chr(10).join(wires)}
{chr(10).join(labels)}
{chr(10).join(ncs)}
\t(sheet_instances
\t\t(path "/"
\t\t\t(page "{page}")
\t\t)
\t)
\t(embedded_fonts no)
)
'''
    path.write_text(text)


def write_root(path, sheets, root_uuid):
    sheet_bodies = []
    y = 30.0
    for filename, title, sheet_uuid, page in sheets:
        sheet_bodies.append(f'''\t(sheet
\t\t(at 25 {fmt(y)})
\t\t(size 120 28)
\t\t(stroke (width 0.15) (type solid))
\t\t(fill (color 0 0 0 0.0000))
\t\t(uuid "{sheet_uuid}")
\t\t(property "Sheetname" "{title}"
\t\t\t(at 25 {fmt(y - 1)} 0)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(property "Sheetfile" "{filename}"
\t\t\t(at 25 {fmt(y + 26)} 0)
\t\t\t(effects (font (size 1.27 1.27)) (hide yes))
\t\t)
\t\t(instances
\t\t\t(project "smartbike_v5"
\t\t\t\t(path "/{root_uuid}"
\t\t\t\t\t(page "{page}")
\t\t\t\t)
\t\t\t)
\t\t)
\t)''')
        y += 34
    text = f'''(kicad_sch
\t(version 20250114)
\t(generator "smartbike_v1")
\t(generator_version "9.0")
\t(uuid "{root_uuid}")
\t(paper "A3")
\t(title_block
\t\t(title "Smart Bike Controller V1")
\t\t(date "2026-10-07")
\t\t(rev "V1")
\t\t(company "Smart Bike V5")
\t\t(comment 1 "70 x 50 mm, 4 layer, 5 V only")
\t)
\t(lib_symbols)
{chr(10).join(sheet_bodies)}
\t(text "PCB Smart Bike V5 — Controller V1. Global labels connect the sheets."
\t\t(at 160 40 0)
\t\t(effects (font (size 2 2)))
\t\t(uuid "{uid("note")}")
\t)
\t(sheet_instances
\t\t(path "/" (page "1"))
\t)
\t(embedded_fonts no)
)
'''
    path.write_text(text)


def drop_footprint_blocks(text):
    """Remove the module's antenna courtyard and the full-board keep-out zone."""
    out = []
    i = 0
    while True:
        k = text.find("\n\t(", i)
        if k < 0:
            out.append(text[i:])
            break
        out.append(text[i : k + 1])
        block, nxt = extract_symbol_span(text, k + 2)
        name = block[1:].split(None, 1)[0]
        if name == "zone" or (name == "fp_line" and "F.CrtYd" in block):
            i = nxt
        else:
            out.append(text[k + 1 : nxt])
            i = nxt
    return "".join(out)


def extract_symbol_span(text, i):
    depth = 0
    j = i
    in_str = False
    while j < len(text):
        c = text[j]
        if in_str:
            if c == "\\":
                j += 2
                continue
            if c == '"':
                in_str = False
            j += 1
            continue
        if c == '"':
            in_str = True
            j += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[i : j + 1], j + 1
        j += 1
    raise ValueError("unclosed footprint block")


def write_esp_module(pretty):
    text = (FP / "RF_Module.pretty" / "ESP32-S3-WROOM-1.kicad_mod").read_text()
    text = drop_footprint_blocks(text)
    # Body courtyard only. The antenna keep-out is the board-edge rule area,
    # not the 48 mm courtyard shipped with the module footprint.
    rect = [(-10.2, -13.8), (10.2, -13.8), (10.2, 14.2), (-10.2, 14.2)]
    lines = []
    for i, (a, b) in enumerate(zip(rect, rect[1:] + rect[:1])):
        lines.append(
            f'\t(fp_line (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) '
            f'(stroke (width 0.05) (type solid)) (layer "F.CrtYd") '
            f'(uuid "{uid("espcrt" + str(i))}"))'
        )
    needle = "\t(embedded_fonts no)"
    if needle not in text:
        raise SystemExit("ESP32 footprint has no embedded_fonts marker")
    text = text.replace(needle, "\n".join(lines) + "\n" + needle, 1)
    (pretty / "ESP32-S3-WROOM-1.kicad_mod").write_text(text)


def write_custom_libs():
    pretty = ROOT / "smartbike.pretty"
    pretty.mkdir(parents=True, exist_ok=True)
    src = (FP / "Package_TO_SOT_SMD.pretty" / "TO-252-2.kicad_mod").read_text()
    src = src.replace('(pad "2"', '(pad "TMP"', 1)
    src = src.replace('(pad "3"', '(pad "2"', 1)
    src = src.replace('(pad "TMP"', '(pad "3"', 1)
    src = src.replace('(footprint "TO-252-2"', '(footprint "TO-252-2_GSD"', 1)
    src = src.replace(
        "TO-252-2",
        "TO-252-2 renumbered GSD: pad 1 gate, pad 2 source, pad 3 drain and tab",
        1,
    )
    (pretty / "TO-252-2_GSD.kicad_mod").write_text(src)
    # BH1750FVI WSOF6, 1.6 mm body. Land pattern is a prototype estimate;
    # confirm against the ROHM WSOF6I drawing before fabrication.
    pads = []
    for i, (x, y) in enumerate([(-0.75, 0.5), (-0.75, 0.0), (-0.75, -0.5), (0.75, -0.5), (0.75, 0.0), (0.75, 0.5)], start=1):
        pads.append(f'''\t(pad "{i}" smd roundrect
\t\t(at {x} {y})
\t\t(size 0.28 0.22)
\t\t(layers "F.Cu" "F.Paste" "F.Mask")
\t\t(roundrect_rratio 0.25)
\t\t(uuid "{uid("bhpad" + str(i))}")
\t)''')
    (pretty / "BH1750FVI_WSOF6.kicad_mod").write_text(f'''(footprint "BH1750FVI_WSOF6"
\t(version 20241229)
\t(generator "smartbike_v1")
\t(layer "F.Cu")
\t(descr "BH1750FVI WSOF6 prototype land. Verify against ROHM jisso drawing before fabrication. No exposed pad.")
\t(attr smd)
\t(property "Reference" "REF**" (at 0 -1.8 0) (layer "F.SilkS") (uuid "{uid("bhref")}") (effects (font (size 0.5 0.5) (thickness 0.08))))
\t(property "Value" "BH1750FVI_WSOF6" (at 0 1.8 0) (layer "F.Fab") (uuid "{uid("bhval")}") (effects (font (size 0.5 0.5) (thickness 0.08))))
\t(property "Datasheet" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{uid("bhds")}") (effects (font (size 0.5 0.5) (thickness 0.08))))
{chr(10).join(pads)}
)
''')
    sym = ROOT / "smartbike.kicad_sym"
    pins = [
        ("1", "VCC", "power_in", -10.16, 5.08, 0),
        ("2", "ADDR", "input", -10.16, 2.54, 0),
        ("3", "GND", "power_in", -10.16, 0, 0),
        ("4", "SDA", "bidirectional", -10.16, -2.54, 0),
        ("5", "DVI", "input", 10.16, 2.54, 180),
        ("6", "SCL", "input", 10.16, 0, 180),
    ]
    pin_txt = []
    for num, name, typ, x, y, ang in pins:
        pin_txt.append(f'''\t\t(pin {typ} line
\t\t\t(at {x} {y} {ang})
\t\t\t(length 2.54)
\t\t\t(name "{name}" (effects (font (size 1.27 1.27))))
\t\t\t(number "{num}" (effects (font (size 1.27 1.27))))
\t\t)''')
    sym.write_text(f'''(kicad_symbol_lib
\t(version 20241209)
\t(generator "smartbike_v1")
\t(symbol "BH1750FVI"
\t\t(pin_names (offset 0.254))
\t\t(exclude_from_sim no)
\t\t(in_bom yes)
\t\t(on_board yes)
\t\t(property "Reference" "U" (at 0 7.62 0) (effects (font (size 1.27 1.27))))
\t\t(property "Value" "BH1750FVI" (at 0 -7.62 0) (effects (font (size 1.27 1.27))))
\t\t(property "Footprint" "smartbike:BH1750FVI_WSOF6" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t(property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t(property "Description" "ROHM BH1750FVI ambient light sensor" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t(symbol "BH1750FVI_0_1"
\t\t\t(rectangle (start -7.62 6.35) (end 7.62 -5.08) (stroke (width 0.254) (type default)) (fill (type background)))
\t\t)
\t\t(symbol "BH1750FVI_1_1"
{chr(10).join(pin_txt)}
\t\t)
\t)
)
''')
    def inlined(libfile, child, parent=None):
        raw = extract_symbol((SYM / libfile).read_text(errors="replace"), parent or child)
        src_name = parent or child
        raw = raw.replace(f'(symbol "{src_name}"', f'(symbol "{child}"', 1)
        raw = raw.replace(f'(symbol "{src_name}_', f'(symbol "{child}_')
        return "\n".join(("\t" + line if line else line) for line in raw.splitlines())

    bmi = extract_symbol((SYM / "Sensor_Motion.kicad_sym").read_text(errors="replace"), "BMI160")
    pin_at = bmi.find("(at -12.7 5.08 0)")
    pin_head = bmi.rfind("(pin bidirectional line", 0, pin_at)
    if pin_head < 0:
        raise SystemExit("BMI160 SDO pin not found")
    bmi = bmi[:pin_head] + "(pin passive line" + bmi[pin_head + len("(pin bidirectional line)") :]
    bmi = bmi.replace('(symbol "BMI160"', '(symbol "BMI270"', 1)
    bmi = bmi.replace('(symbol "BMI160_', '(symbol "BMI270_')
    bmi = "\n".join(("\t" + line if line else line) for line in bmi.splitlines())
    extras = "\n".join([
        inlined("Sensor_Energy.kicad_sym", "INA228", "INA226"),
        inlined("Regulator_Switching.kicad_sym", "TPS62162DSG", "TPS62170DSG"),
        inlined("Power_Protection.kicad_sym", "USBLC6-2SC6", "USBLC6-2P6"),
        bmi,
    ])
    lib_txt = sym.read_text().rstrip()
    if not lib_txt.endswith(")"):
        raise SystemExit("smartbike symbol lib is not closed")
    sym.write_text(lib_txt[:-1] + extras + "\n)\n")
    write_esp_module(pretty)
    # Parser cache must see this library.
    LIBS.files["smartbike.kicad_sym"] = sym.read_text()
    # symbols() reads SYM / filename. Override by preloading the tree from the project file.
    tree = parse_sexp(LIBS.files["smartbike.kicad_sym"])
    LIBS.trees["smartbike.kicad_sym"] = {
        node[1]: node for node in tree[1:] if isinstance(node, list) and node and node[0] == "symbol"
    }


def lib_file_for(lib_id):
    lib = lib_id.split(":")[0]
    if lib == "smartbike":
        return "smartbike.kicad_sym"
    return f"{lib}.kicad_sym"


def patch_embed_path():
    # LibCache.embed_blocks and resolved_pins use SYM / f"{lib}.kicad_sym".
    # smartbike.kicad_sym is preloaded into files/trees, but text() would try SYM.
    # extract_symbol uses text(), so preload is enough if text() is not called for smartbike
    # after files[] is set. text() returns cache. Good.
    pass


# Monkeypatch text() is already cache-first. extract uses text(). Good.


def write_tables():
    sym_table = (KICAD / "template" / "sym-lib-table").read_text()
    sym_table = sym_table.rstrip()
    if sym_table.endswith(")"):
        sym_table = sym_table[:-1] + (
            f'  (lib (name "smartbike")(type "KiCad")(uri "{ROOT / "smartbike.kicad_sym"}")(options "")(descr "V1 project symbols"))\n)\n'
        )
    (ROOT / "sym-lib-table").write_text(sym_table)
    fp_table = (KICAD / "template" / "fp-lib-table").read_text().rstrip()
    if fp_table.endswith(")"):
        fp_table = fp_table[:-1] + (
            f'  (lib (name smartbike)(type KiCad)(uri {ROOT / "smartbike.pretty"})(options "")(descr "V1 project footprints"))\n)\n'
        )
    (ROOT / "fp-lib-table").write_text(fp_table)
    src = KICAD / "demos" / "pic_programmer" / "pic_programmer.kicad_pro"
    shutil.copy(src, ROOT / "smartbike_v5.kicad_pro")


def build_pcb(parts):
    import os
    import pcbnew

    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    design = board.GetDesignSettings()
    # ESP32-S3 module ground vias are 0.2 mm. The copied demo project required 0.3 mm.
    design.m_MinThroughDrill = pcbnew.FromMM(0.2)
    design.m_HoleClearance = pcbnew.FromMM(0.15)
    nets = {}

    def net_of(name):
        if name not in nets:
            item = pcbnew.NETINFO_ITEM(board, name, len(nets) + 1)
            board.Add(item)
            nets[name] = item
        return nets[name]

    print("pcb: loading footprints", flush=True)
    occupied = []

    def load_fp(part):
        lib, name = part.footprint.split(":")
        if lib == "smartbike":
            libdir = str(ROOT / "smartbike.pretty")
        else:
            libdir = str(FP / f"{lib}.pretty")
        fp = pcbnew.FootprintLoad(libdir, name)
        if fp is None:
            raise SystemExit(f"missing footprint {part.footprint}")
        return fp

    def hits(box, gap=0.0):
        x, y, w, h = box
        if x < 0.25 or y < 0.25 or x + w > 69.75 or y + h > 49.75:
            return True
        if x + w > 66.4 and y < 48.0 and y + h > 28.0:
            return True
        if x < 6.1 and y + h > 42.0:
            return True
        for ox, oy, ow, oh in occupied:
            if x < ox + ow + gap and x + w + gap > ox and y < oy + oh + gap and y + h + gap > oy:
                return True
        return False

    def rel_courtyard(fp):
        fp.BuildCourtyardCaches()
        poly = fp.GetCourtyard(pcbnew.F_CrtYd)
        origin = fp.GetPosition()
        if poly.OutlineCount():
            box = poly.BBox()
            xs = [box.GetLeft() - origin.x, box.GetRight() - origin.x]
            ys = [box.GetTop() - origin.y, box.GetBottom() - origin.y]
        else:
            xs, ys = [], []
            for pad in fp.Pads():
                pad_box = pad.GetBoundingBox()
                xs += [pad_box.GetLeft() - origin.x, pad_box.GetRight() - origin.x]
                ys += [pad_box.GetTop() - origin.y, pad_box.GetBottom() - origin.y]
            if not xs:
                return -1.0, -1.0, 1.0, 1.0
        return min(xs) / 1e6, min(ys) / 1e6, max(xs) / 1e6, max(ys) / 1e6

    def finish(part, fp, anchor_x, anchor_y, rel):
        fp.SetReference(part.ref)
        fp.SetValue(part.value)
        if part.dnp and hasattr(fp, "SetDNP"):
            fp.SetDNP(True)
        ref = fp.Reference()
        ref.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(0.4), pcbnew.FromMM(0.4)))
        ref.SetTextThickness(pcbnew.FromMM(0.07))
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(anchor_x), pcbnew.FromMM(anchor_y)))
        for pad in fp.Pads():
            net_name = part.pins.get(pad.GetNumber())
            if net_name:
                pad.SetNet(net_of(net_name))
        x0, y0, x1, y1 = rel
        margin = 0.2
        occupied.append((anchor_x + x0 - margin, anchor_y + y0 - margin, (x1 - x0) + 2 * margin, (y1 - y0) + 2 * margin))

    def place(part, rot, left=None, bottom=None, right=None, top=None):
        fp = load_fp(part)
        fp.SetOrientation(pcbnew.EDA_ANGLE(rot, pcbnew.DEGREES_T))
        fp.SetPosition(pcbnew.VECTOR2I(0, 0))
        board.Add(fp)
        rel = rel_courtyard(fp)
        x0, y0, x1, y1 = rel
        anchor_x = (left - x0) if left is not None else (right - x1)
        anchor_y = (bottom - y0) if bottom is not None else (top - y1)
        world = (anchor_x + x0, anchor_y + y0, x1 - x0, y1 - y0)
        if hits(world):
            nudged = None
            for step in (0.5, 1.0, 1.6, 2.4, 3.2):
                for dx, dy in ((step, 0), (-step, 0), (0, step), (0, -step), (step, step), (-step, step)):
                    trial = (world[0] + dx, world[1] + dy, world[2], world[3])
                    if not hits(trial):
                        nudged = (dx, dy)
                        break
                if nudged:
                    break
            if nudged:
                anchor_x += nudged[0]
                anchor_y += nudged[1]
                print(f"nudged {part.ref} by {nudged[0]:.1f},{nudged[1]:.1f}", flush=True)
            else:
                print(f"place overlap {part.ref}", flush=True)
        finish(part, fp, anchor_x, anchor_y, rel)
        return (anchor_x + x0, anchor_y + y0, x1 - x0, y1 - y0)

    def find_spot(w, h, tight=False):
        y_edge = 49.4 - h
        while y_edge > 0.3:
            x_edge = 0.3
            while x_edge + w < 69.7:
                if not hits((x_edge, y_edge, w, h), gap=-0.35 if tight else 0.0):
                    return x_edge, y_edge
                x_edge += 0.4
            y_edge -= 0.4
        return None

    by_ref = {part.ref: part for part in parts if part.footprint}
    # Antenna end of the module points to the right edge. Courtyard is the
    # module body; the keep-out past it is a rule area.
    place(by_ref["U4"], 270, right=64.8, top=48.2)
    place(by_ref["MOD1"], 0, left=8.2, top=49.4)
    place(by_ref["AE1"], 0, left=8.2, bottom=35.6)
    place(by_ref["U7"], 0, left=12.2, bottom=30.8)
    place(by_ref["U5"], 0, left=27.4, bottom=44.9)
    place(by_ref["U6"], 0, left=25.5, bottom=36.2)
    place(by_ref["U2"], 0, left=12.0, bottom=8.6)
    place(by_ref["U1"], 0, left=24.0, bottom=8.6)
    place(by_ref["U3"], 0, left=51.8, bottom=10.6)
    place(by_ref["SW1"], 0, left=38.2, bottom=18.6)
    place(by_ref["SW2"], 0, left=48.6, bottom=18.6)
    place(by_ref["J2"], 90, left=0.35, bottom=9.8)
    x_edge = 0.35
    for ref in ("J1", "J3", "J4", "J5", "J6", "J7", "J8"):
        world = place(by_ref[ref], 0, left=x_edge, bottom=0.3)
        x_edge += world[2] + 0.35
    placed_refs = {"U4", "MOD1", "AE1", "U7", "U5", "U6", "U2", "U1", "U3", "SW1", "SW2", "J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8"}
    rest = [part for part in parts if part.footprint and part.ref not in placed_refs]
    rest.sort(key=lambda part: (0 if part.sheet == "outputs" else 1, part.ref))
    missed_place = []
    for part in rest:
        fp = load_fp(part)
        fp.SetOrientation(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))
        fp.SetPosition(pcbnew.VECTOR2I(0, 0))
        board.Add(fp)
        rel = rel_courtyard(fp)
        x0, y0, x1, y1 = rel
        spot = find_spot(x1 - x0, y1 - y0)
        if spot is None:
            spot = find_spot(x1 - x0, y1 - y0, tight=True)
        if spot is None:
            missed_place.append(part.ref)
            # Keep the part on the board, in the lower-left service gap, rather than stacking.
            finish(part, fp, 8.0 - x0, 8.0 - y0, rel)
        else:
            finish(part, fp, spot[0] - x0, spot[1] - y0, rel)
    if missed_place:
        print("no free cell for", ", ".join(missed_place))

    print("pcb: outline and zones", flush=True)

    def add_seg(x1, y1, x2, y2, layer):
        shape = pcbnew.PCB_SHAPE(board)
        shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
        shape.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        shape.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        shape.SetLayer(layer)
        shape.SetWidth(pcbnew.FromMM(0.1))
        board.Add(shape)

    for a, b in [((0, 0), (70, 0)), ((70, 0), (70, 50)), ((70, 50), (0, 50)), ((0, 50), (0, 0))]:
        add_seg(a[0], a[1], b[0], b[1], pcbnew.Edge_Cuts)

    def add_zone(layer, net_name, pts, rule=False):
        zone = pcbnew.ZONE(board)
        zone.SetLayer(layer)
        if rule:
            zone.SetIsRuleArea(True)
            zone.SetDoNotAllowCopperPour(True)
            zone.SetDoNotAllowTracks(True)
            zone.SetDoNotAllowVias(True)
            zone.SetDoNotAllowPads(False)
        else:
            zone.SetNet(net_of(net_name))
            zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
            zone.SetMinThickness(pcbnew.FromMM(0.25))
            zone.SetLocalClearance(pcbnew.FromMM(0.2))
        chain = pcbnew.SHAPE_LINE_CHAIN()
        for x, y in pts:
            chain.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
        chain.SetClosed(True)
        zone.Outline().AddOutline(chain)
        if not rule:
            # Keep antenna keep-outs out of the pour.
            zx0, zy0 = min(p[0] for p in pts), min(p[1] for p in pts)
            zx1, zy1 = max(p[0] for p in pts), max(p[1] for p in pts)
            for hx0, hy0, hx1, hy1 in ((66.5, 28.0, 70.0, 48.0), (0.0, 42.0, 6.0, 50.0)):
                ix0, iy0 = max(zx0, hx0), max(zy0, hy0)
                ix1, iy1 = min(zx1, hx1), min(zy1, hy1)
                if ix1 - ix0 < 0.2 or iy1 - iy0 < 0.2:
                    continue
                hole = pcbnew.SHAPE_LINE_CHAIN()
                for x, y in ((ix0, iy0), (ix1, iy0), (ix1, iy1), (ix0, iy1)):
                    hole.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
                hole.SetClosed(True)
                zone.Outline().AddHole(hole)
        board.Add(zone)

    board_pts = [(0.4, 0.4), (69.6, 0.4), (69.6, 49.6), (0.4, 49.6)]
    add_zone(pcbnew.In1_Cu, "GND", board_pts)
    add_zone(pcbnew.F_Cu, "GND", board_pts)
    add_zone(pcbnew.In2_Cu, "+5V_SYS", [(0.6, 0.6), (69.4, 0.6), (69.4, 20.0), (0.6, 20.0)])
    add_zone(pcbnew.In2_Cu, "+3V3", [(0.6, 22.0), (69.4, 22.0), (69.4, 49.4), (0.6, 49.4)])
    # Antenna keep-outs: right edge for ESP32, left-front for GPS.
    for layer in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
        add_zone(layer, "", [(66.5, 48.0), (70.0, 48.0), (70.0, 28.0), (66.5, 28.0)], rule=True)
        add_zone(layer, "", [(0.0, 50.0), (6.0, 50.0), (6.0, 42.0), (0.0, 42.0)], rule=True)

    text = pcbnew.PCB_TEXT(board)
    text.SetText("SMART BIKE V5  PCB V1  5V ONLY")
    text.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(48), pcbnew.FromMM(25)))
    text.SetLayer(pcbnew.F_SilkS)
    text.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(0.7), pcbnew.FromMM(0.7)))
    text.SetTextThickness(pcbnew.FromMM(0.12))
    board.Add(text)

    print("pcb: routing", flush=True)
    route(board)
    # ZONE_FILLER segfaults in this local KiCad 9.0.8 build. The zone outlines
    # are still stored; fill them in the GUI with Edit -> Fill All Zones.
    out = str(ROOT / "smartbike_v5.kicad_pcb")
    pcbnew.SaveBoard(out, board)
    print("wrote", out)


def route(board):
    """Connect every net with tracks and through vias.

    GND stays on In1.Cu. Every other net may use F.Cu, B.Cu and In2.Cu.
    Zone fill is not used: this KiCad build crashes inside ZONE_FILLER.
    """
    import math
    import heapq
    import pcbnew

    F, B = pcbnew.F_Cu, pcbnew.B_Cu
    IN1, IN2 = pcbnew.In1_Cu, pcbnew.In2_Cu
    pitch = 0.25
    cols, rows = int(70 / pitch), int(50 / pitch)
    route_layers = (F, B, IN2)
    occ = {F: {}, B: {}, IN1: {}, IN2: {}}

    def paint(ix, iy, net, layer):
        if ix < 0 or iy < 0 or ix >= cols or iy >= rows:
            return
        cur = occ[layer].get((ix, iy))
        if cur is None:
            occ[layer][(ix, iy)] = net
        elif cur != net:
            occ[layer][(ix, iy)] = "*"

    def mark_rect(x0, y0, x1, y1, net, layer):
        ix0, iy0 = int(x0 / pitch), int(y0 / pitch)
        ix1, iy1 = int(x1 / pitch), int(y1 / pitch)
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                paint(ix, iy, net, layer)

    def mark_disk(x, y, rad, net, layer):
        ix0, iy0 = int((x - rad) / pitch), int((y - rad) / pitch)
        ix1, iy1 = int((x + rad) / pitch), int((y + rad) / pitch)
        r2 = rad * rad
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                cx, cy = (ix + 0.5) * pitch, (iy + 0.5) * pitch
                if (cx - x) ** 2 + (cy - y) ** 2 <= r2:
                    paint(ix, iy, net, layer)

    pads = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net = pad.GetNetname()
            if not net:
                continue
            pos = pad.GetPosition()
            box = pad.GetBoundingBox()
            pads.append({
                "net": net,
                "x": pos.x / 1e6,
                "y": pos.y / 1e6,
                "x0": min(box.GetLeft(), box.GetRight()) / 1e6,
                "y0": min(box.GetTop(), box.GetBottom()) / 1e6,
                "x1": max(box.GetLeft(), box.GetRight()) / 1e6,
                "y1": max(box.GetTop(), box.GetBottom()) / 1e6,
                "tht": pad.GetDrillSize().x > 1000,
                "on_f": pad.IsOnLayer(F),
                "on_b": pad.IsOnLayer(B),
            })

    def keepout(x, y):
        if x < 0.45 or y < 0.45 or x > 69.55 or y > 49.55:
            return True
        if x > 66.5 and 28.0 < y < 48.0:
            return True
        if x < 6.0 and y > 42.0:
            return True
        return False

    for pad in pads:
        layers = (F, B, IN1, IN2) if pad["tht"] else tuple(
            layer for layer, flag in ((F, pad["on_f"]), (B, pad["on_b"])) if flag
        )
        for layer in layers:
            mark_rect(pad["x0"] - 0.12, pad["y0"] - 0.12, pad["x1"] + 0.12, pad["y1"] + 0.12, pad["net"], layer)
    mark_rect(66.5, 28.0, 70.0, 48.0, "KEEP", F)
    mark_rect(66.5, 28.0, 70.0, 48.0, "KEEP", B)
    mark_rect(66.5, 28.0, 70.0, 48.0, "KEEP", IN1)
    mark_rect(66.5, 28.0, 70.0, 48.0, "KEEP", IN2)
    mark_rect(0.0, 42.0, 6.0, 50.0, "KEEP", F)
    mark_rect(0.0, 42.0, 6.0, 50.0, "KEEP", B)
    mark_rect(0.0, 42.0, 6.0, 50.0, "KEEP", IN1)
    mark_rect(0.0, 42.0, 6.0, 50.0, "KEEP", IN2)

    def cell_free(ix, iy, net, layer):
        if ix <= 0 or iy <= 0 or ix >= cols - 1 or iy >= rows - 1:
            return False
        owner = occ[layer].get((ix, iy))
        return owner in (None, net)

    def add_track(x1, y1, x2, y2, layer, net, width):
        if math.hypot(x2 - x1, y2 - y1) < 0.02:
            return
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        track.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        track.SetWidth(pcbnew.FromMM(width))
        track.SetLayer(layer)
        track.SetNet(board.FindNet(net))
        board.Add(track)
        steps = max(1, int(math.hypot(x2 - x1, y2 - y1) / pitch))
        rad = width / 2 + 0.15
        for i in range(steps + 1):
            t = i / steps
            mark_disk(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, rad, net, layer)

    def add_via(x, y, net):
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        via.SetWidth(pcbnew.FromMM(0.6))
        via.SetDrill(pcbnew.FromMM(0.3))
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetNet(board.FindNet(net))
        board.Add(via)
        via_list.append((x, y, net))
        for layer in (F, B, IN1, IN2):
            mark_disk(x, y, 0.45, net, layer)
        # Clearance halos from nearby pads otherwise seal the via into a one-cell pocket.
        ix0, iy0 = int(x / pitch), int(y / pitch)
        for layer in (B, IN1, IN2):
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    if dx * dx + dy * dy > 10:
                        continue
                    cur = occ[layer].get((ix0 + dx, iy0 + dy))
                    if cur in (None, net, "*"):
                        occ[layer][(ix0 + dx, iy0 + dy)] = net

    via_list = []
    near = {}
    for index, pad in enumerate(pads):
        for ix in range(int((pad["x0"] - 1) / 2), int((pad["x1"] + 1) / 2) + 1):
            for iy in range(int((pad["y0"] - 1) / 2), int((pad["y1"] + 1) / 2) + 1):
                near.setdefault((ix, iy), []).append(index)

    def via_ok(x, y, net):
        if keepout(x, y):
            return False
        seen = set()
        for ix in range(int((x - 1.2) / 2), int((x + 1.2) / 2) + 1):
            for iy in range(int((y - 1.2) / 2), int((y + 1.2) / 2) + 1):
                for index in near.get((ix, iy), ()):
                    if index in seen:
                        continue
                    seen.add(index)
                    pad = pads[index]
                    if pad["net"] == net:
                        continue
                    dx = max(pad["x0"] - x, 0, x - pad["x1"])
                    dy = max(pad["y0"] - y, 0, y - pad["y1"])
                    if dx * dx + dy * dy < 0.45 * 0.45:
                        return False
        for vx, vy, vnet in via_list:
            if vnet != net and (x - vx) ** 2 + (y - vy) ** 2 < 0.75 * 0.75:
                return False
        return True

    def emit_path(path, net, width):
        """path items are (x, y, layer)."""
        if len(path) < 2:
            return
        run = [path[0]]
        for pt in path[1:]:
            if pt[2] != run[-1][2]:
                for a, b in zip(run, run[1:]):
                    add_track(a[0], a[1], b[0], b[1], run[-1][2], net, width)
                add_via(run[-1][0], run[-1][1], net)
                run = [pt]
            else:
                run.append(pt)
        for a, b in zip(run, run[1:]):
            add_track(a[0], a[1], b[0], b[1], run[-1][2], net, width)

    def simplify(points):
        if len(points) < 3:
            return points
        out = [points[0]]
        for i in range(1, len(points) - 1):
            ax, ay = out[-1][0], out[-1][1]
            bx, by = points[i][0], points[i][1]
            cx, cy = points[i + 1][0], points[i + 1][1]
            if points[i][2] != out[-1][2] or points[i][2] != points[i + 1][2]:
                out.append(points[i])
            elif abs((bx - ax) * (cy - by) - (by - ay) * (cx - bx)) > 1e-6:
                out.append(points[i])
        out.append(points[-1])
        return out

    def dijkstra(starts, goals, net, allowed):
        goal_at = {}
        for x, y, layer in goals:
            goal_at[(int(x / pitch), int(y / pitch), layer)] = (x, y, layer)
        heap = []
        prev = {}
        best = {}
        for x, y, layer in starts:
            key = (int(x / pitch), int(y / pitch), layer)
            best[key] = 0
            prev[key] = None
            heapq.heappush(heap, (0, key))
        found = None
        while heap:
            cost, key = heapq.heappop(heap)
            if best.get(key, 1e18) != cost:
                continue
            if key in goal_at and key not in { (int(s[0] / pitch), int(s[1] / pitch), s[2]) for s in starts }:
                found = key
                break
            ix, iy, layer = key
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = (ix + dx, iy + dy, layer)
                if not cell_free(nxt[0], nxt[1], net, layer):
                    continue
                ncost = cost + 1
                if ncost < best.get(nxt, 1e18):
                    best[nxt] = ncost
                    prev[nxt] = key
                    heapq.heappush(heap, (ncost, nxt))
            if len(allowed) > 1:
                wx, wy = (ix + 0.5) * pitch, (iy + 0.5) * pitch
                if via_ok(wx, wy, net):
                    for other in allowed:
                        if other == layer:
                            continue
                        nxt = (ix, iy, other)
                        ncost = cost + 14
                        if ncost < best.get(nxt, 1e18):
                            best[nxt] = ncost
                            prev[nxt] = key
                            heapq.heappush(heap, (ncost, nxt))
        if found is None:
            # A goal sharing the start cell is already connected.
            for key, goal in goal_at.items():
                if key in prev:
                    return goal, []
            if len(missed_why) < 3:
                gix, giy, gl = next(iter(goal_at))
                missed_why.append(("search", net, len(prev), cell_free(gix, giy, net, gl), len(goal_at), len(starts)))
            return None
        cur = found
        cells = []
        while cur is not None:
            cells.append(cur)
            cur = prev[cur]
        cells.reverse()
        pts = []
        for ix, iy, layer in cells:
            pts.append(((ix + 0.5) * pitch, (iy + 0.5) * pitch, layer))
        if cells:
            sx = next(s for s in starts if (int(s[0] / pitch), int(s[1] / pitch), s[2]) == cells[0])
            pts[0] = sx
            pts[-1] = goal_at[found]
        return goal_at[found], simplify(pts)

    def connect(net, members, allowed, width):
        if len(members) < 2:
            return True
        pending = members[1:]
        tree = [members[0]]
        guard = 0
        while pending and guard < 400:
            guard += 1
            tree_cells = {}
            for pt in tree:
                tree_cells.setdefault((int(pt[0] / pitch), int(pt[1] / pitch), pt[2]), pt)
            joined = None
            for goal in pending:
                host = tree_cells.get((int(goal[0] / pitch), int(goal[1] / pitch), goal[2]))
                if host is not None:
                    add_track(host[0], host[1], goal[0], goal[1], goal[2], net, width)
                    joined = goal
                    break
            if joined is not None:
                pending.remove(joined)
                tree.append(joined)
                continue
            found = dijkstra(tree, pending, net, allowed)
            if found is None:
                return False
            goal, path = found
            emit_path(path, net, width)
            pending.remove(goal)
            tree.append(goal)
        return not pending

    by_net = {}
    for pad in pads:
        by_net.setdefault(pad["net"], []).append(pad)

    def terminals(group, layer):
        out = []
        for pad in group:
            use = layer
            if layer == F and not pad["on_f"] and not pad["tht"]:
                use = B if pad["on_b"] else F
            out.append((pad["x"], pad["y"], use))
        return out

    def segment_free(x1, y1, x2, y2, net, layer):
        steps = max(1, int(math.hypot(x2 - x1, y2 - y1) / pitch))
        for i in range(steps + 1):
            t = i / steps
            ix = int((x1 + (x2 - x1) * t) / pitch)
            iy = int((y1 + (y2 - y1) * t) / pitch)
            if not cell_free(ix, iy, net, layer):
                return False
        return True

    def escape_to_back(pad, net, width):
        if pad["tht"]:
            return (pad["x"], pad["y"], B)
        for dist in (6.5, 4.8, 3.2, 2.0, 1.15, 0.0):
            angles = (0,) if dist == 0.0 else range(0, 360, 30)
            for deg in angles:
                rad = math.radians(deg)
                vx = pad["x"] + math.cos(rad) * dist
                vy = pad["y"] + math.sin(rad) * dist
                if not via_ok(vx, vy, net):
                    continue
                if dist > 0 and not segment_free(pad["x"], pad["y"], vx, vy, net, F):
                    continue
                if dist > 0:
                    add_track(pad["x"], pad["y"], vx, vy, F, net, min(width, 0.3))
                add_via(vx, vy, net)
                return (vx, vy, B)
        return None

    def punch_pads(group, net):
        for pad in group:
            ix0, iy0 = int(pad["x"] / pitch), int(pad["y"] / pitch)
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    cur = occ[F].get((ix0 + dx, iy0 + dy))
                    if cur in (None, net, "*"):
                        occ[F][(ix0 + dx, iy0 + dy)] = net

    def route_front_then_back(name, group, width, max_los=28):
        punch_pads(group, name)
        fronts = [(pad["x"], pad["y"], F) for pad in group]
        if connect(name, fronts, (F,), width):
            return True
        parent = list(range(len(group)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        pairs = []
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                dist = math.hypot(group[i]["x"] - group[j]["x"], group[i]["y"] - group[j]["y"])
                if dist <= max_los:
                    pairs.append((dist, i, j))
        pairs.sort()
        for _, i, j in pairs:
            if find(i) == find(j):
                continue
            if segment_free(group[i]["x"], group[i]["y"], group[j]["x"], group[j]["y"], name, F):
                add_track(group[i]["x"], group[i]["y"], group[j]["x"], group[j]["y"], F, name, width)
                parent[find(j)] = find(i)
        clusters = {}
        for i in range(len(group)):
            clusters.setdefault(find(i), []).append(i)
        if len(clusters) == 1:
            return True
        reps = []
        for cluster in clusters.values():
            point = None
            for index in cluster:
                point = escape_to_back(group[index], name, width)
                if point is not None:
                    break
            if point is None:
                if len(missed_why) < 6:
                    missed_why.append((name, "via"))
                return False
            reps.append(point)
        powerish = name.startswith("+5") or name.startswith("USB_VBUS") or name.endswith("_N")
        first, second = (B, IN2) if powerish else (IN2, B)
        if connect(name, reps, (first,), width):
            return True
        if connect(name, reps, (second,), width):
            return True
        if len(missed_why) < 8:
            missed_why.append((name, "layers", len(reps)))
        return False

    missed = []
    missed_why = []
    ordered = sorted(
        (name for name in by_net if name != "GND"),
        key=lambda name: -len(by_net[name]),
    )
    for name in ordered:
        group = by_net[name]
        power = name in ("+5V_SYS", "+3V3", "+5V_IN", "+5V_FUSED", "+5V_PROT", "+5V_MERGED", "USB_VBUS", "USB_VBUS_FUSED", "HORN_N")
        width = 0.4 if power else 0.25
        if not route_front_then_back(name, group, width, max_los=8 if power else 22):
            missed.append(name)
            print("miss", name, len(group), flush=True)
    gnd = by_net.get("GND", [])
    gnd_pts = []
    for pad in gnd:
        if pad["tht"]:
            gnd_pts.append((pad["x"], pad["y"], IN1))
            continue
        placed = None
        for dist in (0.0, 0.85, 1.2, 1.7):
            angles = (0,) if dist == 0 else range(0, 360, 30)
            for deg in angles:
                rad = math.radians(deg)
                vx = pad["x"] + math.cos(rad) * dist
                vy = pad["y"] + math.sin(rad) * dist
                if dist == 0:
                    vx, vy = pad["x"], pad["y"]
                if not via_ok(vx, vy, "GND"):
                    continue
                if dist > 0:
                    add_track(pad["x"], pad["y"], vx, vy, F, "GND", 0.3)
                add_via(vx, vy, "GND")
                placed = (vx, vy, IN1)
                break
            if placed:
                break
        if placed:
            gnd_pts.append(placed)
        else:
            missed.append("GND")
    if gnd_pts and not connect("GND", gnd_pts, (IN1,), 0.4):
        if "GND" not in missed:
            missed.append("GND")
    missed = sorted(set(missed))
    if missed:
        print("unrouted", len(missed), " ".join(missed), flush=True)
        print("why", missed_why, flush=True)
    else:
        print("all nets routed", flush=True)



def main():
    # Re-running this replaces smartbike_v5.kicad_pcb, including copper
    # imported from the Freerouting session in fab/smartbike.ses.
    print("regenerating schematic and PCB; this replaces existing copper")
    ROOT.mkdir(parents=True, exist_ok=True)
    write_custom_libs()
    parts = build_parts()
    root_uuid = uid("root-sheet")
    order = [
        ("power.kicad_sch", "Power", "power", "2"),
        ("usb.kicad_sch", "USB", "usb", "3"),
        ("mcu.kicad_sch", "MCU", "mcu", "4"),
        ("sensors.kicad_sch", "Sensors", "sensors", "5"),
        ("gps.kicad_sch", "GPS", "gps", "6"),
        ("outputs.kicad_sch", "Outputs", "outputs", "7"),
        ("handlebar.kicad_sch", "Handlebar", "handlebar", "8"),
    ]
    sheet_meta = []
    for filename, title, sheet, page in order:
        group = [part for part in parts if part.sheet == sheet]
        pack_sheet(group)
        sheet_uuid = uid("sheet:" + sheet)
        write_sheet(ROOT / filename, title, group, root_uuid, sheet_uuid, page)
        sheet_meta.append((filename, title, sheet_uuid, page))
        print(f"{sheet}: {len(group)} symbols")
    write_root(ROOT / "smartbike_v5.kicad_sch", sheet_meta, root_uuid)
    write_tables()
    build_pcb(parts)


if __name__ == "__main__":
    main()
