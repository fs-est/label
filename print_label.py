"""
print_label.py
Shared library and CLI for generating and printing Estino labels.

CLI usage:
    python print_label.py --serial "000000002138" --part "22.000.7600.64.8"
    python print_label.py --serial "000000002138" --part "22.000.7600.64.8" --preview

Requires:
    pip install pillow qrcode[pil] pyyaml pymupdf
"""

import argparse
import subprocess
from pathlib import Path

import pymupdf as fitz
import qrcode
import yaml
from PIL import Image, ImageDraw, ImageFont

def resource_path(relative: str) -> Path:
    import sys
    if getattr(sys, 'frozen', False):
        # Running as exe, look next to the exe
        base = Path(sys.executable).parent
    else:
        # Running as script
        base = Path(__file__).parent
    return base / relative

def get_brother_ql_path() -> str:
    import sys
    if getattr(sys, 'frozen', False):
        return str(Path(sys.executable).parent / "brother_ql.exe")
    return r"C:\Users\fs\AppData\Local\Python\pythoncore-3.14-64\Scripts\brother_ql.exe"

BROTHER_QL = get_brother_ql_path()

CONFIG_PATH = resource_path("label_config.yaml")
QR_BASE_URL = "https://qr.myestino.de/edge/"


# ── config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


# ── printer discovery ─────────────────────────────────────────────────────────
''' old code for reference, may be useful for debugging:
def discover_printer() -> str | None:
    try:
        result = subprocess.run(
            [BROTHER_QL, "-b", "pyusb", "discover"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=8
        )
        combined = (result.stdout + result.stderr).decode("utf-8", errors="replace")
        for line in combined.splitlines():
            line = line.strip()
            print(f"DEBUG: {repr(line)}")
            if line.startswith("usb://"):
                # Strip any suffix after the product ID (e.g. _Љ)
                import re
                line = re.sub(r'(usb://0x[0-9a-fA-F]+:0x[0-9a-fA-F]+).*', r'\1', line)
                return line
    except Exception as e:
        print(f"Discover error: {e}")
    return None
'''
def discover_printer() -> str | None:
    """Find QL-800 via pyusb directly, bypassing brother_ql CLI."""
    try:
        import usb.core
        device = usb.core.find(idVendor=0x04f9)
        if device is not None:
            return f"usb://0x{device.idVendor:04x}:0x{device.idProduct:04x}"
    except Exception as e:
        print(f"Discover error: {e}")
    return None

# ── label generation ──────────────────────────────────────────────────────────

def generate_qr(url: str, size_px: int) -> Image.Image:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=0,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return img.resize((size_px, size_px), Image.LANCZOS)


def build_label(serial: str, part: str, config: dict) -> Image.Image:
    cfg = config
    url = QR_BASE_URL + serial

    # Load template (PDF or PNG)
    template_path = resource_path(cfg["template"]["path"])
    if template_path.suffix.lower() == ".pdf":
        doc = fitz.open(template_path)
        page = doc[0]
        mat = fitz.Matrix(cfg["label"]["dpi"] / 72, cfg["label"]["dpi"] / 72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
        label = Image.frombytes("L", (pix.width, pix.height), pix.samples).convert("RGB")
    else:
        label = Image.open(template_path).convert("RGB")

    # Ensure correct dimensions
    expected = (cfg["label"]["width_px"], cfg["label"]["height_px"])
    if label.size != expected:
        print(f"Warning: template size {label.size} differs from config {expected}, resizing.")
        label = label.resize(expected, Image.LANCZOS)

    draw = ImageDraw.Draw(label)

    # Load fonts
    try:
        font_label = ImageFont.truetype(
            cfg["font"]["label"]["path"], cfg["font"]["label"]["size"])
        font_value = ImageFont.truetype(
            cfg["font"]["value"]["path"], cfg["font"]["value"]["size"])
    except IOError as e:
        print(f"Warning: font error ({e}), falling back to default.")
        font_label = ImageFont.load_default()
        font_value = ImageFont.load_default()

    line_gap = 4

    # Draw part number
    pn = cfg["elements"]["part_number"]
    draw.text((pn["x"], pn["y"]), pn["label"], fill="black", font=font_label)
    draw.text((pn["x"], pn["y"] + cfg["font"]["label"]["size"] + line_gap),
              part, fill="black", font=font_value)

    # Draw serial number
    sn = cfg["elements"]["serial_number"]
    draw.text((sn["x"], sn["y"]), sn["label"], fill="black", font=font_label)
    draw.text((sn["x"], sn["y"] + cfg["font"]["label"]["size"] + line_gap),
              serial, fill="black", font=font_value)

    # Paste QR code
    qr_cfg = cfg["elements"]["qr_code"]
    qr_img = generate_qr(url, qr_cfg["size"])
    label.paste(qr_img, (qr_cfg["x"], qr_cfg["y"]))

    # Rotate for printing if needed
    rotate_deg = cfg["label"].get("rotate_for_print", 0)
    if rotate_deg:
        label = label.rotate(rotate_deg, expand=True)

    return label


# ── printing ──────────────────────────────────────────────────────────────────

def send_to_printer(output_path: Path, config: dict, printer_uri: str) -> tuple[bool, str]:
    """Send a PNG to the printer. Returns (success, error_message)."""
    roll_width = config["label"]["roll_width_mm"]
    cmd = [
        BROTHER_QL,
        "-b", "pyusb",
        "-m", "QL-800",
        "-p", printer_uri,
        "print",
        "-l", str(roll_width),
        "--600dpi",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0, result.stdout + result.stderr


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate and print an Estino product label.")
    parser.add_argument("--serial", required=True, help="Serial number")
    parser.add_argument("--part", required=True, help="Part number")
    parser.add_argument("--preview", action="store_true",
                        help="Save output PNG but do not print")
    args = parser.parse_args()

    config = load_config()
    label = build_label(args.serial, args.part, config)

    output_path = Path.home() / "AppData" / "Local" / "Temp" / "label_output.png"
    label.save(output_path)
    print(f"Label saved to {output_path}")

    if args.preview:
        return

    printer_uri = discover_printer()
    if not printer_uri:
        print("Error: no printer found. Is the QL-800 connected?")
        return

    success, err = send_to_printer(output_path, config, printer_uri)
    if success:
        print("Printed successfully.")
    else:
        print(f"Print error: {err}")


if __name__ == "__main__":
    main()
