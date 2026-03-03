"""
label_gui.py - Estino Label Printer GUI
"""

import subprocess
import threading
from io import BytesIO
from pathlib import Path

import pymupdf as fitz
import qrcode
import yaml
from PIL import Image, ImageDraw, ImageFont, ImageTk
import tkinter as tk
from tkinter import ttk, messagebox


CONFIG_PATH = Path(__file__).parent / "label_config.yaml"
BROTHER_QL = r"C:\Users\fs\AppData\Local\Python\pythoncore-3.14-64\Scripts\brother_ql.exe"
ZADIG_URL = "https://zadig.akeo.ie"


# ── helpers ──────────────────────────────────────────────────────────────────

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def discover_printer():
    """Return USB identifier string or None."""
    try:
        result = subprocess.run(
            [BROTHER_QL, "-b", "pyusb", "discover"],
            capture_output=True, text=True, timeout=5
        )
        combined = result.stdout + result.stderr
        for line in combined.splitlines():
            line = line.strip()
            if line.startswith("usb://"):
                return line
    except Exception:
        pass
    return None


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


def build_label(url: str, serial: str, part: str, config: dict) -> Image.Image:
    cfg = config
    template_path = Path(__file__).parent / cfg["template"]["path"]

    if template_path.suffix.lower() == ".pdf":
        doc = fitz.open(template_path)
        page = doc[0]
        mat = fitz.Matrix(cfg["label"]["dpi"] / 72, cfg["label"]["dpi"] / 72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
        label = Image.frombytes("L", (pix.width, pix.height), pix.samples).convert("RGB")
    else:
        label = Image.open(template_path).convert("RGB")

    expected = (cfg["label"]["width_px"], cfg["label"]["height_px"])
    if label.size != expected:
        label = label.resize(expected, Image.LANCZOS)

    draw = ImageDraw.Draw(label)

    try:
        font_label = ImageFont.truetype(cfg["font"]["label"]["path"], cfg["font"]["label"]["size"])
        font_value = ImageFont.truetype(cfg["font"]["value"]["path"], cfg["font"]["value"]["size"])
    except IOError:
        font_label = ImageFont.load_default()
        font_value = ImageFont.load_default()

    pn_cfg = cfg["elements"]["part_number"]
    draw.text((pn_cfg["x"], pn_cfg["y"]), pn_cfg["label"], fill="black", font=font_label)
    draw.text((pn_cfg["x"], pn_cfg["y"] + cfg["font"]["label"]["size"] + 4), part, fill="black", font=font_value)

    sn_cfg = cfg["elements"]["serial_number"]
    draw.text((sn_cfg["x"], sn_cfg["y"]), sn_cfg["label"], fill="black", font=font_label)
    draw.text((sn_cfg["x"], sn_cfg["y"] + cfg["font"]["label"]["size"] + 4), serial, fill="black", font=font_value)

    qr_cfg = cfg["elements"]["qr_code"]
    qr_img = generate_qr(url, qr_cfg["size"])
    label.paste(qr_img, (qr_cfg["x"], qr_cfg["y"]))

    rotate_deg = cfg["label"].get("rotate_for_print", 0)
    if rotate_deg:
        label = label.rotate(rotate_deg, expand=True)

    return label


def send_to_printer(output_path: Path, config: dict, printer_uri: str):
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
    return result.returncode == 0, result.stderr


# ── GUI ───────────────────────────────────────────────────────────────────────

class LabelPrinterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Estino Label Printer")
        self.resizable(False, False)
        self.configure(bg="#F5F5F3")

        self.config_data = load_config()
        self.printer_uri = None
        self.preview_image = None

        self._build_ui()
        self._discover_printer()

    def _build_ui(self):
        FONT_TITLE = ("Segoe UI", 13, "bold")
        FONT_LABEL = ("Segoe UI", 10)
        FONT_SMALL = ("Segoe UI", 9)
        BG = "#F5F5F3"
        CARD = "#FFFFFF"
        ACCENT = "#1A1A1A"
        BORDER = "#E0E0DC"
        GREEN = "#2D7D46"
        RED = "#C0392B"

        # ── header
        header = tk.Frame(self, bg=ACCENT, padx=24, pady=16)
        header.pack(fill="x")
        tk.Label(header, text="ESTINO", font=("Segoe UI", 11, "bold"),
                 bg=ACCENT, fg="#FFFFFF").pack(side="left")
        tk.Label(header, text="Label Printer", font=("Segoe UI", 11),
                 bg=ACCENT, fg="#AAAAAA").pack(side="left", padx=(8, 0))

        # ── printer status bar
        status_bar = tk.Frame(self, bg=BORDER, padx=24, pady=10)
        status_bar.pack(fill="x")
        tk.Label(status_bar, text="Printer", font=FONT_SMALL,
                 bg=BORDER, fg="#666666").pack(side="left")
        self.status_dot = tk.Label(status_bar, text="●", font=("Segoe UI", 12),
                                   bg=BORDER, fg="#CCCCCC")
        self.status_dot.pack(side="left", padx=(8, 4))
        self.status_label = tk.Label(status_bar, text="Searching…",
                                     font=FONT_SMALL, bg=BORDER, fg="#666666")
        self.status_label.pack(side="left")

        setup_btn = tk.Button(status_bar, text="Setup USB Driver",
                              font=FONT_SMALL, bg=BORDER, fg="#444444",
                              relief="flat", cursor="hand2",
                              command=self._open_zadig)
        setup_btn.pack(side="right")

        # ── main content
        content = tk.Frame(self, bg=BG, padx=24, pady=20)
        content.pack(fill="both", expand=True)

        # left: form
        form_frame = tk.Frame(content, bg=CARD, padx=20, pady=20,
                              relief="flat", bd=1, highlightbackground=BORDER,
                              highlightthickness=1)
        form_frame.pack(side="left", fill="y")

        tk.Label(form_frame, text="Serial No.", font=FONT_LABEL,
                 bg=CARD, fg="#444444").pack(anchor="w")
        self.serial_var = tk.StringVar()
        self.serial_entry = ttk.Entry(form_frame, textvariable=self.serial_var,
                                      width=28, font=FONT_LABEL)
        self.serial_entry.pack(anchor="w", pady=(4, 0))

        self.url_preview = tk.Label(form_frame, text="https://qr.myestino.de/edge/",
                                    font=("Segoe UI", 8), bg=CARD, fg="#AAAAAA")
        self.url_preview.pack(anchor="w", pady=(2, 16))

        tk.Label(form_frame, text="Part No.", font=FONT_LABEL,
                 bg=CARD, fg="#444444").pack(anchor="w")
        self.part_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.part_var,
                  width=28, font=FONT_LABEL).pack(anchor="w", pady=(4, 24))

        self.print_btn = tk.Button(
            form_frame, text="Print Label",
            font=("Segoe UI", 11, "bold"),
            bg=ACCENT, fg="white",
            activebackground="#333333", activeforeground="white",
            relief="flat", padx=20, pady=10,
            cursor="hand2", command=self._on_print
        )
        self.print_btn.pack(fill="x")

        self.feedback_label = tk.Label(form_frame, text="", font=FONT_SMALL,
                                       bg=CARD, fg=GREEN, wraplength=220)
        self.feedback_label.pack(pady=(10, 0))

        # right: preview
        preview_frame = tk.Frame(content, bg=BG, padx=16)
        preview_frame.pack(side="left", fill="both", expand=True)

        tk.Label(preview_frame, text="Preview", font=FONT_SMALL,
                 bg=BG, fg="#AAAAAA").pack(anchor="w", pady=(0, 6))

        self.preview_canvas = tk.Label(preview_frame, bg=BORDER,
                                       width=280, height=180,
                                       text="Fill in the fields\nto see a preview",
                                       font=FONT_SMALL, fg="#AAAAAA",
                                       relief="flat")
        self.preview_canvas.pack()

        # bindings
        self.serial_var.trace_add("write", self._update_url_preview)
        self.serial_var.trace_add("write", lambda *_: self._refresh_preview())
        self.part_var.trace_add("write", lambda *_: self._refresh_preview())

    def _update_url_preview(self, *_):
        serial = self.serial_var.get()
        self.url_preview.config(
            text=f"https://qr.myestino.de/edge/{serial}"
        )

    def _refresh_preview(self):
        serial = self.serial_var.get().strip()
        part = self.part_var.get().strip()
        if not serial or not part:
            return
        threading.Thread(target=self._generate_preview,
                         args=(serial, part), daemon=True).start()

    def _generate_preview(self, serial, part):
        try:
            url = f"https://qr.myestino.de/edge/{serial}"
            img = build_label(url, serial, part, self.config_data)
            # scale to fit preview area
            img.thumbnail((280, 180), Image.LANCZOS)
            self.preview_image = ImageTk.PhotoImage(img)
            self.after(0, lambda: self.preview_canvas.config(
                image=self.preview_image, text=""))
        except Exception as e:
            self.after(0, lambda: self.preview_canvas.config(
                text=f"Preview error:\n{e}", image=""))

    def _discover_printer(self):
        def run():
            uri = discover_printer()
            self.printer_uri = uri
            if uri:
                self.after(0, lambda: self._set_status(True, uri))
            else:
                self.after(0, lambda: self._set_status(False, "Not found. Connect printer and restart."))
        threading.Thread(target=run, daemon=True).start()

    def _set_status(self, connected: bool, text: str):
        self.status_dot.config(fg="#2D7D46" if connected else "#C0392B")
        self.status_label.config(text=text)

    def _open_zadig(self):
        import webbrowser
        webbrowser.open(ZADIG_URL)

    def _on_print(self):
        serial = self.serial_var.get().strip()
        part = self.part_var.get().strip()

        if not serial or not part:
            messagebox.showwarning("Missing fields", "Please fill in both Serial No. and Part No.")
            return

        if not self.printer_uri:
            messagebox.showerror("No printer", "No printer found. Connect the QL-800 and restart the app.")
            return

        self.print_btn.config(state="disabled", text="Printing…")
        self.feedback_label.config(text="", fg="#2D7D46")

        def run():
            try:
                url = f"https://qr.myestino.de/edge/{serial}"
                img = build_label(url, serial, part, self.config_data)
                output_path = Path(__file__).parent / self.config_data["output"]["path"]
                img.save(output_path)
                success, err = send_to_printer(output_path, self.config_data, self.printer_uri)
                if success:
                    self.after(0, lambda: self.feedback_label.config(
                        text="✓ Printed successfully.", fg="#2D7D46"))
                else:
                    self.after(0, lambda: self.feedback_label.config(
                        text=f"Print error: {err}", fg="#C0392B"))
            except Exception as e:
                self.after(0, lambda: self.feedback_label.config(
                    text=f"Error: {e}", fg="#C0392B"))
            finally:
                self.after(0, lambda: self.print_btn.config(
                    state="normal", text="Print Label"))

        threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    app = LabelPrinterApp()
    app.mainloop()
