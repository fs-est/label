"""
print_label.py
Usage:
    python print_label.py --url "https://example.com" --serial "SN-12345" --part "PN-6789"

Requires:
    pip install pillow qrcode[pil] pyyaml
"""

import argparse
import subprocess
from pathlib import Path

import qrcode
import yaml
from PIL import Image, ImageDraw, ImageFont


BROTHER_QL = r"C:\Users\fs\AppData\Local\Python\pythoncore-3.14-64\Scripts\brother_ql.exe"
PRINTER_URI = "usb://0x04f9:0x209b"
CONFIG_PATH = Path(__file__).parent / "label_config.yaml"


def load_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


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
    img = img.resize((size_px, size_px), Image.LANCZOS)
    return img


def build_label(url: str, serial: str, part: str, config: dict) -> Image.Image:
    cfg = config

    # Load template (for label_template.png)
    # template_path = Path(__file__).parent / cfg["template"]["path"]
    # label = Image.open(template_path).convert("RGB")

    # Load template (for label_template.pdf)
    import pymupdf as fitz  # pymupdf

    template_path = Path(__file__).parent / cfg["template"]["path"]
    if template_path.suffix.lower() == ".pdf":
        doc = fitz.open(template_path)
        page = doc[0]
        mat = fitz.Matrix(cfg["label"]["dpi"] / 72, cfg["label"]["dpi"] / 72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
        label = Image.frombytes("L", (pix.width, pix.height), pix.samples).convert("RGB")
    else:
        label = Image.open(template_path).convert("RGB")

    # Resize to exact spec if needed
    expected = (cfg["label"]["width_px"], cfg["label"]["height_px"])
    if label.size != expected:
        print(f"Warning: template size {label.size} differs from config {expected}, resizing.")
        label = label.resize(expected, Image.LANCZOS)

    draw = ImageDraw.Draw(label)

    # Load fonts
    try:
        font_label = ImageFont.truetype(cfg["font"]["label"]["path"], cfg["font"]["label"]["size"])
        font_value = ImageFont.truetype(cfg["font"]["value"]["path"], cfg["font"]["value"]["size"])
    except IOError:
        print("Warning: font not found, falling back to default.")
        font_label = ImageFont.load_default()
        font_value = ImageFont.load_default()

    # Draw part number
    pn_cfg = cfg["elements"]["part_number"]
    draw.text((pn_cfg["x"], pn_cfg["y"]), pn_cfg["label"], fill="black", font=font_label)
    draw.text((pn_cfg["x"], pn_cfg["y"] + cfg["font"]["label"]["size"] + 4), part, fill="black", font=font_value)

    # Draw serial number
    sn_cfg = cfg["elements"]["serial_number"]
    draw.text((sn_cfg["x"], sn_cfg["y"]), sn_cfg["label"], fill="black", font=font_label)
    draw.text((sn_cfg["x"], sn_cfg["y"] + cfg["font"]["label"]["size"] + 4), serial, fill="black", font=font_value)

    # Paste QR code
    qr_cfg = cfg["elements"]["qr_code"]
    qr_img = generate_qr(url, qr_cfg["size"])
    label.paste(qr_img, (qr_cfg["x"], qr_cfg["y"]))

    # Rotate for printing
    rotate_deg = cfg["label"].get("rotate_for_print", 0)
    if rotate_deg:
        label = label.rotate(rotate_deg, expand=True)

    return label


def print_label(output_path: Path, config: dict):
    roll_width = config["label"]["roll_width_mm"]
    cmd = [
        BROTHER_QL,
        "-b", "pyusb",
        "-m", "QL-800",
        "-p", PRINTER_URI,
        "print",
        "-l", str(roll_width),
        str(output_path),
    ]
    print(f"Sending to printer: {output_path}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("Print error:")
        print(result.stderr)
    else:
        print("Printed successfully.")


def main():
    parser = argparse.ArgumentParser(description="Generate and print a product label.")
    parser.add_argument("--url", required=True, help="URL for the QR code")
    parser.add_argument("--serial", required=True, help="Serial number")
    parser.add_argument("--part", required=True, help="Part number")
    parser.add_argument("--preview", action="store_true", help="Save output PNG but do not print")
    args = parser.parse_args()

    config = load_config()
    label = build_label(args.url, args.serial, args.part, config)

    output_path = Path(__file__).parent / config["output"]["path"]
    label.save(output_path)
    print(f"Label saved to {output_path}")

    if not args.preview:
        print_label(output_path, config)


if __name__ == "__main__":
    main()
