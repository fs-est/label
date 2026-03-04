"""
label_gui.py - Estino Label Printer GUI
Run with: python label_gui.py
"""

import sys
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, messagebox

sys.path.insert(0, str(Path(__file__).parent))
from print_label import load_config, discover_printer, build_label, send_to_printer


class LabelPrinterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Estino Label Printer")
        self.resizable(False, False)
        self.configure(bg="#F5F5F3")
        self.config_data = load_config()
        self.printer_uri = None
        self.preview_image = None
        self._preview_job = None
        # Check required files exist
        from print_label import resource_path
        missing = [f for f in ["label_config.yaml", "label_template.pdf"]
                if not resource_path(f).exists()]
        if missing:
            import tkinter.messagebox as mb
            mb.showerror("Missing files",
                        f"Could not find:\n" + "\n".join(
                            str(resource_path(f)) for f in missing))
            self.destroy()
            return
        self._build_ui()
        self._discover_printer()

    def _build_ui(self):
        FONT_LABEL = ("Segoe UI", 10)
        FONT_SMALL = ("Segoe UI", 9)
        BG = "#F5F5F3"
        CARD = "#FFFFFF"
        ACCENT = "#1A1A1A"
        BORDER = "#E0E0DC"
        GREEN = "#2D7D46"

        header = tk.Frame(self, bg=ACCENT, padx=24, pady=16)
        header.pack(fill="x")
        tk.Label(header, text="ESTINO", font=("Segoe UI", 11, "bold"),
                 bg=ACCENT, fg="#FFFFFF").pack(side="left")
        tk.Label(header, text="Label Printer", font=("Segoe UI", 11),
                 bg=ACCENT, fg="#AAAAAA").pack(side="left", padx=(8, 0))

        status_bar = tk.Frame(self, bg=BORDER, padx=24, pady=10)
        status_bar.pack(fill="x")
        tk.Label(status_bar, text="Printer", font=FONT_SMALL,
                 bg=BORDER, fg="#666666").pack(side="left")
        self.status_dot = tk.Label(status_bar, text="●", font=("Segoe UI", 12),
                                   bg=BORDER, fg="#CCCCCC")
        self.status_dot.pack(side="left", padx=(8, 4))
        self.status_label = tk.Label(status_bar, text="Searching...",
                                     font=FONT_SMALL, bg=BORDER, fg="#666666")
        self.status_label.pack(side="left")
        tk.Button(status_bar, text="Setup USB Driver", font=FONT_SMALL,
                  bg=BORDER, fg="#444444", relief="flat", cursor="hand2",
                  command=self._open_zadig).pack(side="right")

        content = tk.Frame(self, bg=BG, padx=24, pady=20)
        content.pack(fill="both", expand=True)

        form_frame = tk.Frame(content, bg=CARD, padx=20, pady=20,
                              relief="flat", bd=1,
                              highlightbackground=BORDER, highlightthickness=1)
        form_frame.pack(side="left", fill="y")

        tk.Label(form_frame, text="Serial No.", font=FONT_LABEL,
                 bg=CARD, fg="#444444").pack(anchor="w")
        self.serial_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.serial_var,
                  width=28, font=FONT_LABEL).pack(anchor="w", pady=(4, 0))
        self.url_preview = tk.Label(form_frame,
                                    text="https://qr.myestino.de/edge/",
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

        preview_frame = tk.Frame(content, bg=BG, padx=16)
        preview_frame.pack(side="left", fill="both", expand=True)
        tk.Label(preview_frame, text="Preview", font=FONT_SMALL,
                 bg=BG, fg="#AAAAAA").pack(anchor="w", pady=(0, 6))
        self.preview_canvas = tk.Label(
            preview_frame, bg=BORDER, width=280, height=180,
            text="Fill in the fields\nto see a preview",
            font=FONT_SMALL, fg="#AAAAAA", relief="flat"
        )
        self.preview_canvas.pack()

        self.serial_var.trace_add("write", self._on_serial_change)
        self.part_var.trace_add("write", self._on_field_change)

    def _on_serial_change(self, *_):
        self.url_preview.config(
            text=f"https://qr.myestino.de/edge/{self.serial_var.get()}")
        self._schedule_preview()

    def _on_field_change(self, *_):
        self._schedule_preview()

    def _schedule_preview(self):
        if self._preview_job:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(400, self._trigger_preview)

    def _trigger_preview(self):
        self._preview_job = None
        serial = self.serial_var.get().strip()
        part = self.part_var.get().strip()
        if serial and part:
            threading.Thread(target=self._generate_preview,
                             args=(serial, part), daemon=True).start()

    def _generate_preview(self, serial, part):
        try:
            img = build_label(serial, part, self.config_data)
            img.thumbnail((280, 180), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.after(0, lambda: self._set_preview(photo))
        except Exception as e:
            self.after(0, lambda: self.preview_canvas.config(
                text=f"Preview error:\n{e}", image=""))

    def _set_preview(self, photo):
        self.preview_image = photo
        self.preview_canvas.config(image=photo, text="")

    def _discover_printer(self):
        def run():
            uri = discover_printer()
            self.printer_uri = uri
            if uri:
                self.after(0, lambda: self._set_status(True, uri))
            else:
                self.after(0, lambda: self._set_status(
                    False, "Not found. Connect printer and restart."))
        threading.Thread(target=run, daemon=True).start()

    def _set_status(self, connected, text):
        self.status_dot.config(fg="#2D7D46" if connected else "#C0392B")
        self.status_label.config(text=text)

    def _open_zadig(self):
        import webbrowser
        webbrowser.open("https://zadig.akeo.ie")

    def _on_print(self):
        serial = self.serial_var.get().strip()
        part = self.part_var.get().strip()
        if not serial or not part:
            messagebox.showwarning("Missing fields",
                                   "Please fill in both Serial No. and Part No.")
            return
        if not self.printer_uri:
            messagebox.showerror("No printer",
                                 "No printer found. Connect the QL-800 and restart.")
            return

        self.print_btn.config(state="disabled", text="Printing...")
        self.feedback_label.config(text="")

        def run():
            try:
                img = build_label(serial, part, self.config_data)
                output_path = Path(tempfile.gettempdir()) / "label_output.png"
                img.save(output_path)
                success, err = send_to_printer(output_path, self.config_data, self.printer_uri)
                if success:
                    self.after(0, lambda: self.feedback_label.config(
                        text="Printed successfully.", fg="#2D7D46"))
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
