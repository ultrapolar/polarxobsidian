"""Minimal Tkinter GUI for the PDF highlight extractor.

Pick a scanned-book PDF, enter a Title/Author, and click Extract. The pipeline
runs on a background thread and writes both a Readwise CSV and an Excel workbook
next to the PDF (named after the PDF). Progress streams into the status box.

Launch with:  python gui.py
"""

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from main import process_pdf


class HighlightExtractorGUI:
    def __init__(self, root):
        self.root = root
        root.title("PDF Highlight Extractor → Readwise")
        root.minsize(560, 420)

        self.pdf_path = None
        self.reference_paths = []
        self.log_queue = queue.Queue()
        self.worker = None

        self._build_widgets()
        self._poll_log_queue()

    # ------------------------------------------------------------------ UI
    def _build_widgets(self):
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(self.root)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        # Input picker — a PDF, or a folder of page images
        ttk.Label(frm, text="Input:").grid(row=0, column=0, sticky="w", **pad)
        self.pdf_label = ttk.Label(frm, text="(none selected)", foreground="gray")
        self.pdf_label.grid(row=0, column=1, sticky="we", **pad)
        pick = ttk.Frame(frm)
        pick.grid(row=0, column=2, **pad)
        ttk.Button(pick, text="PDF…", command=self._browse).grid(row=0, column=0)
        ttk.Button(pick, text="Image folder…",
                   command=self._browse_image_folder).grid(row=0, column=1, padx=(4, 0))

        # Title
        ttk.Label(frm, text="Title:").grid(row=1, column=0, sticky="w", **pad)
        self.title_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.title_var).grid(
            row=1, column=1, columnspan=2, sticky="we", **pad
        )

        # Author
        ttk.Label(frm, text="Author:").grid(row=2, column=0, sticky="w", **pad)
        self.author_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.author_var).grid(
            row=2, column=1, columnspan=2, sticky="we", **pad
        )

        # Reference sources (optional) — correct OCR errors. Multiple allowed:
        # ebook/PDF/text and/or an audiobook (file or folder), combined.
        ttk.Label(frm, text="References\n(optional):").grid(
            row=3, column=0, sticky="nw", **pad
        )
        ref_frame = ttk.Frame(frm)
        ref_frame.grid(row=3, column=1, columnspan=2, sticky="we", **pad)
        ref_frame.columnconfigure(0, weight=1)
        self.ref_list = tk.Listbox(ref_frame, height=3)
        self.ref_list.grid(row=0, column=0, rowspan=3, sticky="we")
        ttk.Button(ref_frame, text="Add file…", command=self._add_ref_file).grid(
            row=0, column=1, sticky="we", padx=(6, 0)
        )
        ttk.Button(ref_frame, text="Add audio folder…",
                   command=self._add_ref_folder).grid(
            row=1, column=1, sticky="we", padx=(6, 0)
        )
        ttk.Button(ref_frame, text="Clear", command=self._clear_refs).grid(
            row=2, column=1, sticky="we", padx=(6, 0)
        )

        # Output folder (informational)
        ttk.Label(frm, text="Output:").grid(row=4, column=0, sticky="w", **pad)
        self.output_label = ttk.Label(
            frm, text="(saved next to the PDF)", foreground="gray"
        )
        self.output_label.grid(row=4, column=1, columnspan=2, sticky="we", **pad)

        # Action buttons
        btns = ttk.Frame(frm)
        btns.grid(row=5, column=0, columnspan=3, **pad)
        self.extract_btn = ttk.Button(
            btns, text="Extract highlights", command=self._on_extract
        )
        self.extract_btn.grid(row=0, column=0, padx=4)
        self.transcribe_btn = ttk.Button(
            btns, text="Transcribe audio only…", command=self._on_transcribe
        )
        self.transcribe_btn.grid(row=0, column=1, padx=4)

        # Status log
        ttk.Label(frm, text="Status:").grid(row=6, column=0, sticky="nw", **pad)
        self.status = tk.Text(frm, height=12, wrap="word", state="disabled")
        self.status.grid(row=6, column=1, columnspan=2, sticky="nsew", **pad)
        frm.rowconfigure(6, weight=1)

    # -------------------------------------------------------------- actions
    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select a PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not path:
            return
        self.pdf_path = path
        self.pdf_label.config(text=path, foreground="black")
        self.output_label.config(
            text=os.path.dirname(path) or ".", foreground="black"
        )
        # Pre-fill title from the filename if empty
        if not self.title_var.get().strip():
            stem = os.path.splitext(os.path.basename(path))[0]
            self.title_var.set(stem)

    def _browse_image_folder(self):
        path = filedialog.askdirectory(
            title="Select a folder of page images (photos/scans)"
        )
        if not path:
            return
        self.pdf_path = path
        self.pdf_label.config(text=path, foreground="black")
        self.output_label.config(
            text=os.path.dirname(path) or ".", foreground="black"
        )
        if not self.title_var.get().strip():
            self.title_var.set(os.path.basename(path.rstrip("/\\")))

    def _add_ref_file(self):
        paths = filedialog.askopenfilenames(
            title="Add reference file(s): ebook, PDF, text, or audio",
            filetypes=[
                ("Reference / audio",
                 "*.epub *.pdf *.txt *.mp3 *.m4a *.m4b *.wav *.flac *.ogg"),
                ("All files", "*.*"),
            ],
        )
        for p in paths:
            self._add_ref(p)

    def _add_ref_folder(self):
        path = filedialog.askdirectory(
            title="Add an audiobook folder (contains MP3/M4B files)"
        )
        if path:
            self._add_ref(path)

    def _add_ref(self, path):
        if path not in self.reference_paths:
            self.reference_paths.append(path)
            self.ref_list.insert("end", path)

    def _clear_refs(self):
        self.reference_paths.clear()
        self.ref_list.delete(0, "end")

    def _on_extract(self):
        if not self.pdf_path:
            messagebox.showwarning(
                "No PDF", "Please choose a PDF file first."
            )
            return
        if self.worker and self.worker.is_alive():
            return

        self._clear_status()
        self.extract_btn.config(state="disabled")
        self.transcribe_btn.config(state="disabled")

        output_base = os.path.splitext(self.pdf_path)[0]
        self.worker = threading.Thread(
            target=self._run_pipeline,
            args=(self.pdf_path, output_base,
                  self.title_var.get().strip(),
                  self.author_var.get().strip(),
                  list(self.reference_paths)),
            daemon=True,
        )
        self.worker.start()

    def _run_pipeline(self, pdf_path, output_base, title, author, references):
        """Runs on a background thread. Communicates via the log queue."""
        def log(msg):
            self.log_queue.put(("log", str(msg)))

        try:
            csv_path, xlsx_path = process_pdf(
                pdf_path, output_base, title=title, author=author,
                references=references, log=log,
            )
            self.log_queue.put(("done", (csv_path, xlsx_path)))
        except Exception as exc:  # surface any failure to the GUI
            self.log_queue.put(("error", str(exc)))

    def _on_transcribe(self):
        if self.worker and self.worker.is_alive():
            return
        paths = filedialog.askopenfilenames(
            title="Select audiobook file(s) to transcribe",
            filetypes=[
                ("Audio", "*.mp3 *.m4a *.m4b *.wav *.flac *.ogg *.opus"),
                ("All files", "*.*"),
            ],
        )
        if not paths:
            return
        self._clear_status()
        self.extract_btn.config(state="disabled")
        self.transcribe_btn.config(state="disabled")
        self.worker = threading.Thread(
            target=self._run_transcribe, args=(list(paths),), daemon=True
        )
        self.worker.start()

    def _run_transcribe(self, paths):
        """Transcribe audio on a background thread; transcripts are cached."""
        def log(msg):
            self.log_queue.put(("log", str(msg)))

        try:
            import audio_transcriber
            outputs = []
            for p in paths:
                log(f"Transcribing {os.path.basename(p)} ...")
                audio_transcriber.transcribe(p, log=log)
                outputs.append(audio_transcriber._cache_path(p))
            self.log_queue.put(("transcribed", outputs))
        except Exception as exc:
            self.log_queue.put(("error", str(exc)))

    # ----------------------------------------------------------- log pump
    def _poll_log_queue(self):
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "log":
                    self._append_status(payload)
                elif kind == "done":
                    csv_path, xlsx_path = payload
                    self.extract_btn.config(state="normal")
                    self.transcribe_btn.config(state="normal")
                    messagebox.showinfo(
                        "Done",
                        "Extraction complete.\n\n"
                        f"Readwise CSV:\n{csv_path}\n\n"
                        f"Excel workbook:\n{xlsx_path}\n\n"
                        "Obsidian notes (full text + highlights) saved alongside "
                        "— see the status log for paths.",
                    )
                elif kind == "transcribed":
                    self.extract_btn.config(state="normal")
                    self.transcribe_btn.config(state="normal")
                    messagebox.showinfo(
                        "Transcription complete",
                        "Saved transcript(s):\n\n" + "\n".join(payload),
                    )
                elif kind == "error":
                    self.extract_btn.config(state="normal")
                    self.transcribe_btn.config(state="normal")
                    self._append_status(f"ERROR: {payload}")
                    messagebox.showerror("Error", payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log_queue)

    # --------------------------------------------------------- status box
    def _append_status(self, text):
        self.status.config(state="normal")
        self.status.insert("end", text + "\n")
        self.status.see("end")
        self.status.config(state="disabled")

    def _clear_status(self):
        self.status.config(state="normal")
        self.status.delete("1.0", "end")
        self.status.config(state="disabled")


def main():
    root = tk.Tk()
    HighlightExtractorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
