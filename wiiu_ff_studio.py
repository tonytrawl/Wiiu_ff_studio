"""
Wii U Fastfile Studio
=====================

A small desktop front-end for working with Black Ops II (T6) Wii U fastfiles:

  * decrypt + decompress a Wii U `.ff` into its raw zone
  * repack a zone back into a valid Wii U v148 fastfile
  * validate a zone against genuine Wii U structural conventions
  * drive the extended OpenAssetTools build to write big-endian v148 zones
    and to dump the decompressed content of a fastfile

Pure standard library (tkinter) -- no third-party imports -- so it runs
anywhere Python 3 does and freezes cleanly to a single EXE.
"""
import os
import sys
import io
import queue
import threading
import subprocess
import contextlib
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

import wiiu_ff
import zone_validate
import ff_assets

APP_TITLE = "Wii U Fastfile Studio"
APP_VERSION = "1.0"

# Default location of the extended OpenAssetTools Unlinker, relative to this app.
# Drop the build next to the app (or set the path in the OAT tabs).
OAT_DEFAULT_CANDIDATES = [
    os.path.join(APP_DIR, "oat", "Unlinker.exe"),
    os.path.join(APP_DIR, "Unlinker.exe"),
]

# ---- palette --------------------------------------------------------------
BG      = "#0f1420"
CARD    = "#1a2233"
HEADER  = "#0b0f18"
ACCENT  = "#18b4a8"
ACCENT2 = "#0e8f86"
TEXT    = "#e6edf3"
MUTED   = "#9aa7b8"
BORDER  = "#26324a"
FIELD   = "#0c1220"


def find_oat_default():
    for c in OAT_DEFAULT_CANDIDATES:
        if os.path.isfile(c):
            return c
    return ""


class Studio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} {APP_VERSION}")
        self.geometry("980x720")
        self.minsize(820, 600)
        self.configure(bg=BG)
        try:
            self.iconbitmap(os.path.join(getattr(sys, "_MEIPASS", APP_DIR), "studio.ico"))
        except Exception:
            pass
        self._busy = False
        self._logq = queue.Queue()
        self._style()
        self._banner()
        self._body()
        self._statusbar()
        self.after(60, self._drain_log)

    # -- theming ------------------------------------------------------------
    def _style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        st.configure("TFrame", background=BG)
        st.configure("Card.TFrame", background=CARD)
        st.configure("TLabel", background=BG, foreground=TEXT)
        st.configure("Card.TLabel", background=CARD, foreground=TEXT)
        st.configure("H.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI Semibold", 13))
        st.configure("Sub.TLabel", background=CARD, foreground=MUTED, font=("Segoe UI", 9))
        st.configure("TCheckbutton", background=CARD, foreground=TEXT)
        st.map("TCheckbutton", background=[("active", CARD)])
        st.configure("TEntry", fieldbackground=FIELD, foreground=TEXT, bordercolor=BORDER,
                     insertcolor=TEXT)
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", background=HEADER, foreground=MUTED,
                     padding=(18, 9), font=("Segoe UI", 10))
        st.map("TNotebook.Tab",
               background=[("selected", CARD)],
               foreground=[("selected", ACCENT)])
        st.configure("Accent.TButton", background=ACCENT, foreground="#03110f",
                     font=("Segoe UI Semibold", 10), borderwidth=0, padding=(14, 8))
        st.map("Accent.TButton", background=[("active", ACCENT2), ("disabled", BORDER)])
        st.configure("Ghost.TButton", background=CARD, foreground=TEXT,
                     borderwidth=1, padding=(10, 6))
        st.map("Ghost.TButton", background=[("active", BORDER)])
        st.configure("TProgressbar", background=ACCENT, troughcolor=HEADER, borderwidth=0)

    def _banner(self):
        bar = tk.Frame(self, bg=HEADER, height=58)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="  Wii U Fastfile Studio", bg=HEADER, fg=TEXT,
                 font=("Segoe UI Semibold", 16)).pack(side="left", pady=10)
        tk.Label(bar, text="T6  .ff  /  v148  /  big-endian   ", bg=HEADER, fg=ACCENT,
                 font=("Segoe UI", 10)).pack(side="right", pady=14)
        tk.Frame(self, bg=ACCENT, height=2).pack(fill="x")

    def _body(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(10, 6))
        self._tab_decrypt(nb)
        self._tab_repack(nb)
        self._tab_validate(nb)
        self._tab_ff_editor(nb)
        self._tab_oat_convert(nb)
        self._tab_oat_dump(nb)
        self._tab_about(nb)
        self._log_pane()

    def _log_pane(self):
        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=False, padx=12, pady=(0, 6))
        head = tk.Frame(wrap, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="Output log", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        ttk.Button(head, text="Clear", style="Ghost.TButton",
                   command=lambda: self.log.delete("1.0", "end")).pack(side="right")
        box = tk.Frame(wrap, bg=BORDER)
        box.pack(fill="both", expand=True, pady=(4, 0))
        self.log = tk.Text(box, height=11, bg=FIELD, fg="#cfe9e5", insertbackground=TEXT,
                           relief="flat", wrap="word", font=("Consolas", 9), bd=0)
        sb = ttk.Scrollbar(box, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True, padx=1, pady=1)

    def _statusbar(self):
        bar = tk.Frame(self, bg=HEADER, height=26)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self.status = tk.Label(bar, text="Ready", bg=HEADER, fg=MUTED,
                               font=("Segoe UI", 9))
        self.status.pack(side="left", padx=10)
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=150)
        self.progress.pack(side="right", padx=10, pady=4)

    # -- helpers ------------------------------------------------------------
    def _card(self, parent, title, subtitle):
        outer = ttk.Frame(parent, padding=14)
        outer.pack(fill="both", expand=True)
        card = tk.Frame(outer, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="both", expand=True)
        pad = ttk.Frame(card, style="Card.TFrame", padding=18)
        pad.pack(fill="both", expand=True)
        ttk.Label(pad, text=title, style="H.TLabel").pack(anchor="w")
        ttk.Label(pad, text=subtitle, style="Sub.TLabel").pack(anchor="w", pady=(2, 14))
        return pad

    def _file_row(self, parent, label, var, save=False, types=None, dirpick=False):
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, style="Card.TLabel", width=16).pack(side="left")
        ent = ttk.Entry(row, textvariable=var)
        ent.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def browse():
            if dirpick:
                p = filedialog.askdirectory()
            elif save:
                p = filedialog.asksaveasfilename(filetypes=types or [])
            else:
                p = filedialog.askopenfilename(filetypes=types or [])
            if p:
                var.set(p)
        ttk.Button(row, text="Browse", style="Ghost.TButton", command=browse).pack(side="left")
        return ent

    def _run_btn(self, parent, text, fn):
        b = ttk.Button(parent, text=text, style="Accent.TButton", command=fn)
        b.pack(anchor="w", pady=(16, 0))
        return b

    def log_line(self, s):
        self._logq.put(s)

    def _drain_log(self):
        try:
            while True:
                s = self._logq.get_nowait()
                self.log.insert("end", s + "\n")
                self.log.see("end")
        except queue.Empty:
            pass
        self.after(60, self._drain_log)

    def _set_busy(self, on, msg="Ready"):
        self._busy = on
        self.status.config(text=msg)
        if on:
            self.progress.start(12)
        else:
            self.progress.stop()

    def _task(self, name, fn):
        if self._busy:
            messagebox.showinfo(APP_TITLE, "A task is already running.")
            return
        self._set_busy(True, name + "...")
        self.log_line(f"\n=== {name} ===")

        def worker():
            try:
                fn()
                self.log_line(f"[done] {name}")
                self.after(0, lambda: self._set_busy(False, "Done"))
            except Exception as e:
                self.log_line(f"[error] {e}")
                self.after(0, lambda: self._set_busy(False, "Error"))
        threading.Thread(target=worker, daemon=True).start()

    # -- tab: decrypt -------------------------------------------------------
    def _tab_decrypt(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="Decrypt")
        p = self._card(f, "Fastfile  ->  Zone",
                       "Decrypt and decompress a Wii U .ff into its raw decompressed zone.")
        self.d_in = tk.StringVar()
        self.d_out = tk.StringVar()
        self._file_row(p, "Wii U fastfile", self.d_in,
                       types=[("Fastfile", "*.ff"), ("All files", "*.*")])
        self._file_row(p, "Output zone", self.d_out, save=True,
                       types=[("Zone", "*.zone")])

        def go():
            src = self.d_in.get().strip()
            if not os.path.isfile(src):
                raise FileNotFoundError("Select a valid .ff file")
            data = open(src, "rb").read()
            if not wiiu_ff.is_wiiu_fastfile(data):
                raise ValueError("Not a Wii U (v148) fastfile")
            hdr, zone, n = wiiu_ff.decrypt(data)
            out = self.d_out.get().strip() or os.path.splitext(src)[0] + ".zone"
            open(out, "wb").write(zone)
            self.log_line(f"name='{hdr['name']}'  chunks={n}")
            self.log_line(f"decompressed zone = {len(zone):,} bytes")
            self.log_line(f"wrote {out}")
        self._run_btn(p, "Decrypt + Decompress", lambda: self._task("Decrypt", go))

    # -- tab: repack --------------------------------------------------------
    def _tab_repack(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="Repack")
        p = self._card(f, "Zone  ->  Fastfile",
                       "Pack a decompressed zone back into a Wii U v148 fastfile.")
        self.r_in = tk.StringVar()
        self.r_name = tk.StringVar()
        self.r_out = tk.StringVar()
        e = self._file_row(p, "Zone", self.r_in, types=[("Zone", "*.zone"), ("All files", "*.*")])

        def autoname(*_):
            base = os.path.splitext(os.path.basename(self.r_in.get()))[0]
            if base and not self.r_name.get():
                self.r_name.set(base)
        self.r_in.trace_add("write", autoname)
        nr = ttk.Frame(p, style="Card.TFrame")
        nr.pack(fill="x", pady=4)
        ttk.Label(nr, text="Internal name", style="Card.TLabel", width=16).pack(side="left")
        ttk.Entry(nr, textvariable=self.r_name).pack(side="left", fill="x", expand=True)
        self._file_row(p, "Output fastfile", self.r_out, save=True, types=[("Fastfile", "*.ff")])
        ttk.Label(p, text="The internal name must match the slot the game loads it as.",
                  style="Sub.TLabel").pack(anchor="w", pady=(6, 0))

        def go():
            src = self.r_in.get().strip()
            if not os.path.isfile(src):
                raise FileNotFoundError("Select a valid .zone file")
            name = self.r_name.get().strip() or os.path.splitext(os.path.basename(src))[0]
            zone = open(src, "rb").read()
            ff = wiiu_ff.pack(zone, name)
            out = self.r_out.get().strip() or os.path.splitext(src)[0] + "_repacked.ff"
            open(out, "wb").write(ff)
            self.log_line(f"packed {len(zone):,} byte zone -> {len(ff):,} byte ff")
            self.log_line(f"name='{name}'  wrote {out}")
        self._run_btn(p, "Pack Fastfile", lambda: self._task("Repack", go))

    # -- tab: validate ------------------------------------------------------
    def _tab_validate(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="Validate")
        p = self._card(f, "Structural Zone Validator",
                       "Check a decompressed zone against genuine Wii U structural conventions.")
        self.v_in = tk.StringVar()
        self.v_ref = tk.StringVar()
        self._file_row(p, "Zone", self.v_in, types=[("Zone", "*.zone"), ("All files", "*.*")])
        self._file_row(p, "Reference (opt)", self.v_ref,
                       types=[("Zone", "*.zone"), ("All files", "*.*")])
        disclaimer = (
            "What this checks: the structure of a SINGLE zone against Wii U loader conventions — "
            "block policy (TEMP stays small / data in VIRTUAL), the XAssetList follow-pointers, the "
            "script-string table, and the asset-directory entries. It's a load-time sanity gate that "
            "flags a skeleton the loader would choke on.\n"
            "What it does NOT do: it is not a comparison or content check. It does not diff two zones "
            "and says nothing about assets, scripts, geometry, platform or endianness. The optional "
            "reference is only printed alongside for eyeballing — it is never compared — so two "
            "different zones can both pass."
        )
        ttk.Label(p, text=disclaimer, style="Sub.TLabel", wraplength=820,
                  justify="left").pack(anchor="w", pady=(8, 0))

        def go():
            src = self.v_in.get().strip()
            if not os.path.isfile(src):
                raise FileNotFoundError("Select a valid .zone file")
            buf = io.StringIO()
            argv = [src]
            ref = self.v_ref.get().strip()
            if ref:
                argv += ["--ref", ref]
            old = sys.argv
            sys.argv = ["zone_validate"] + argv
            try:
                with contextlib.redirect_stdout(buf):
                    rc = zone_validate.main()
            finally:
                sys.argv = old
            for ln in buf.getvalue().splitlines():
                self.log_line(ln)
            self.log_line("VALIDATION PASSED" if rc == 0 else "VALIDATION FOUND DIVERGENCES")
        self._run_btn(p, "Validate Zone", lambda: self._task("Validate", go))

    # -- tab: FF editor -----------------------------------------------------
    def _tab_ff_editor(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="Zone editor")
        p = self._card(f, "Browse & Edit Zone Contents",
                       "List the scripts (GSC/CSC) and rawfiles inside a zone, export them, and "
                       "replace them in place before repacking.")
        self.fe_zone = None
        self.fe_path = ""
        self.fe_entries = []

        self.fe_in = tk.StringVar()
        row = ttk.Frame(p, style="Card.TFrame")
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Zone", style="Card.TLabel", width=14).pack(side="left")
        ttk.Entry(row, textvariable=self.fe_in).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(row, text="Browse", style="Ghost.TButton",
                   command=lambda: self.fe_in.set(filedialog.askopenfilename(
                       filetypes=[("Zone", "*.zone"), ("All files", "*.*")]) or self.fe_in.get())
                   ).pack(side="left")
        ttk.Button(row, text="Open", style="Accent.TButton", command=self._fe_open).pack(side="left", padx=(8, 0))

        # tree
        st = ttk.Style(self)
        st.configure("FE.Treeview", background=FIELD, fieldbackground=FIELD, foreground=TEXT,
                     rowheight=22, borderwidth=0)
        st.configure("FE.Treeview.Heading", background=HEADER, foreground=MUTED,
                     font=("Segoe UI", 9))
        st.map("FE.Treeview", background=[("selected", ACCENT2)], foreground=[("selected", "#03110f")])
        tw = tk.Frame(p, bg=BORDER)
        tw.pack(fill="both", expand=True, pady=(10, 6))
        cols = ("kind", "size", "name")
        self.fe_tree = ttk.Treeview(tw, columns=cols, show="headings", style="FE.Treeview", height=10)
        self.fe_tree.heading("kind", text="Kind")
        self.fe_tree.heading("size", text="Size")
        self.fe_tree.heading("name", text="Name")
        self.fe_tree.column("kind", width=80, anchor="w", stretch=False)
        self.fe_tree.column("size", width=90, anchor="e", stretch=False)
        self.fe_tree.column("name", width=560, anchor="w")
        sb = ttk.Scrollbar(tw, command=self.fe_tree.yview)
        self.fe_tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.fe_tree.pack(side="left", fill="both", expand=True, padx=1, pady=1)

        btns = ttk.Frame(p, style="Card.TFrame")
        btns.pack(fill="x")
        ttk.Button(btns, text="Export selected", style="Ghost.TButton",
                   command=self._fe_export).pack(side="left")
        ttk.Button(btns, text="Replace selected (in-place)", style="Ghost.TButton",
                   command=self._fe_replace).pack(side="left", padx=8)
        ttk.Button(btns, text="Save zone", style="Accent.TButton",
                   command=self._fe_save).pack(side="right")
        ttk.Label(p, text="Replacement must be the exact same byte length (in-place edit). To resize a "
                          "script, recompile to the same length or rebuild via the OAT GSC-inject path.",
                  style="Sub.TLabel", wraplength=820, justify="left").pack(anchor="w", pady=(8, 0))

    def _fe_open(self):
        src = self.fe_in.get().strip()
        if not os.path.isfile(src):
            messagebox.showerror(APP_TITLE, "Select a valid .zone file")
            return
        try:
            self.fe_zone = open(src, "rb").read()
            self.fe_path = src
            self.fe_entries = ff_assets.scan_buffers(self.fe_zone)
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))
            return
        for r in self.fe_tree.get_children():
            self.fe_tree.delete(r)
        for i, e in enumerate(self.fe_entries):
            self.fe_tree.insert("", "end", iid=str(i),
                                values=(e["kind"], f"{e['len']:,}", e["name"]))
        ns = sum(1 for e in self.fe_entries if e["kind"] == "script")
        nr = sum(1 for e in self.fe_entries if e["kind"] == "rawfile")
        self.log_line(f"\n=== FF Editor: opened {os.path.basename(src)} ===")
        self.log_line(f"found {len(self.fe_entries)} editable assets  (scripts={ns} rawfiles={nr})")

    def _fe_selected(self):
        sel = self.fe_tree.selection()
        if not sel or self.fe_zone is None:
            messagebox.showinfo(APP_TITLE, "Open a zone and select an entry first.")
            return None
        return self.fe_entries[int(sel[0])]

    def _fe_export(self):
        e = self._fe_selected()
        if not e:
            return
        base = os.path.basename(e["name"]) or "asset.bin"
        out = filedialog.asksaveasfilename(initialfile=base)
        if not out:
            return
        open(out, "wb").write(ff_assets.extract_buffer(self.fe_zone, e))
        self.log_line(f"exported '{e['name']}' ({e['len']:,} bytes) -> {out}")

    def _fe_replace(self):
        e = self._fe_selected()
        if not e:
            return
        src = filedialog.askopenfilename(title=f"Replacement for {e['name']} (must be {e['len']:,} bytes)")
        if not src:
            return
        data = open(src, "rb").read()
        try:
            self.fe_zone = ff_assets.replace_buffer(self.fe_zone, e, data)
        except ValueError as ex:
            messagebox.showerror(APP_TITLE, str(ex))
            self.log_line(f"[replace rejected] {ex}")
            return
        self.log_line(f"replaced '{e['name']}' in place ({e['len']:,} bytes). Save the zone to keep it.")

    def _fe_save(self):
        if self.fe_zone is None:
            messagebox.showinfo(APP_TITLE, "Nothing to save.")
            return
        out = filedialog.asksaveasfilename(
            initialfile=os.path.basename(self.fe_path) or "edited.zone",
            filetypes=[("Zone", "*.zone")])
        if not out:
            return
        open(out, "wb").write(self.fe_zone)
        self.log_line(f"saved edited zone -> {out}  (now repack it with the Repack tab)")

    # -- OAT path field reused across the two OAT tabs ----------------------
    def _oat_row(self, parent, var):
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Unlinker.exe", style="Card.TLabel", width=16).pack(side="left")
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, padx=(0, 8))

        def browse():
            p = filedialog.askopenfilename(filetypes=[("Unlinker", "Unlinker.exe"), ("All", "*.*")])
            if p:
                var.set(p)
        ttk.Button(row, text="Browse", style="Ghost.TButton", command=browse).pack(side="left")

    def _run_oat(self, exe, ff_path, env_extra, cwd_out):
        if not os.path.isfile(exe):
            raise FileNotFoundError("Point 'Unlinker.exe' at the extended OpenAssetTools build")
        if not os.path.isfile(ff_path):
            raise FileNotFoundError("Select a valid fastfile")
        work = os.path.dirname(os.path.abspath(cwd_out)) or "."
        # Unlinker name-verifies the file against its internal name; stage a copy named to match.
        try:
            data = open(ff_path, "rb").read()
            internal = data[24:56].split(b"\x00")[0].decode("latin1") or os.path.splitext(os.path.basename(ff_path))[0]
        except Exception:
            internal = os.path.splitext(os.path.basename(ff_path))[0]
        staged = os.path.join(work, internal + ".ff")
        if os.path.abspath(staged) != os.path.abspath(ff_path):
            open(staged, "wb").write(open(ff_path, "rb").read())
        env = dict(os.environ)
        env.update(env_extra)
        self.log_line(f"$ Unlinker --list {internal}.ff   ({' '.join(k+'='+v for k,v in env_extra.items())})")
        proc = subprocess.Popen([exe, "--list", staged], cwd=work,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                env=env, text=True, bufsize=1)
        for line in proc.stdout:
            self.log_line(line.rstrip())
        proc.wait()
        return proc.returncode, work, internal

    # -- tab: OAT convert ---------------------------------------------------
    def _tab_oat_convert(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="OAT: Write Wii U Zone")
        p = self._card(f, "Write a big-endian v148 Wii U zone",
                       "Load a fastfile through the extended OpenAssetTools and re-emit it as a "
                       "big-endian Wii U (v148) zone with the Wii U write-path transforms applied.")
        self.c_oat = tk.StringVar(value=find_oat_default())
        self.c_in = tk.StringVar()
        self._oat_row(p, self.c_oat)
        self._file_row(p, "Source fastfile", self.c_in,
                       types=[("Fastfile", "*.ff"), ("All files", "*.*")])

        opts = ttk.Frame(p, style="Card.TFrame")
        opts.pack(fill="x", pady=(10, 0))
        self.c_sig = tk.BooleanVar(value=True)
        self.c_rtphys = tk.BooleanVar(value=True)
        self.c_dropgsc = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Ignore signature check (read unsigned)",
                        variable=self.c_sig).pack(anchor="w")
        ttk.Checkbutton(opts, text="Reserve RUNTIME_PHYSICAL block (0xc60000)",
                        variable=self.c_rtphys).pack(anchor="w")
        ttk.Checkbutton(opts, text="Drop script (scriptparsetree) assets",
                        variable=self.c_dropgsc).pack(anchor="w")
        ttk.Label(p, text="Output is written next to the source as <name>_rewrite.ff (a raw v148 zone). "
                          "Block-policy remap, inline-image stripping and the Wii U asset-type / mapents "
                          "remap are applied automatically by the write path.",
                  style="Sub.TLabel", wraplength=820, justify="left").pack(anchor="w", pady=(10, 0))

        def go():
            env = {"OAT_REWRITE": "1", "OAT_WRITE_WIIU": "1"}
            if self.c_sig.get():
                env["OAT_IGNORE_SIG"] = "1"
            if self.c_rtphys.get():
                env["OAT_RT_PHYS"] = "c60000"
            if self.c_dropgsc.get():
                env["OAT_DROP_GSC"] = "1"
            rc, work, internal = self._run_oat(self.c_oat.get().strip(), self.c_in.get().strip(),
                                               env, self.c_in.get().strip())
            out = os.path.join(work, internal + "_rewrite.ff")
            if os.path.isfile(out):
                self.log_line(f"wrote raw Wii U zone -> {out} ({os.path.getsize(out):,} bytes)")
                self.log_line("Pack it with the Repack tab to produce a loadable .ff.")
            else:
                self.log_line(f"(exit {rc}) no _rewrite.ff produced - see log above")
        self._run_btn(p, "Write Wii U Zone", lambda: self._task("OAT write Wii U zone", go))

    # -- tab: OAT dump ------------------------------------------------------
    def _tab_oat_dump(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="OAT: Dump Zone")
        p = self._card(f, "Dump the decompressed zone content",
                       "Decompress a fastfile through the extended OpenAssetTools and write its raw "
                       "decompressed content to a file (works even when the asset graph can't be fully parsed).")
        self.u_oat = tk.StringVar(value=find_oat_default())
        self.u_in = tk.StringVar()
        self.u_out = tk.StringVar()
        self._oat_row(p, self.u_oat)
        self._file_row(p, "Source fastfile", self.u_in,
                       types=[("Fastfile", "*.ff"), ("All files", "*.*")])
        self._file_row(p, "Output .bin", self.u_out, save=True, types=[("Binary", "*.bin")])
        self.u_sig = tk.BooleanVar(value=True)
        ttk.Checkbutton(p, text="Ignore signature check", variable=self.u_sig).pack(anchor="w", pady=(8, 0))

        def go():
            outp = self.u_out.get().strip() or os.path.splitext(self.u_in.get().strip())[0] + "_content.bin"
            env = {"OAT_DUMP_ZONE": os.path.abspath(outp)}
            if self.u_sig.get():
                env["OAT_IGNORE_SIG"] = "1"
            rc, work, internal = self._run_oat(self.u_oat.get().strip(), self.u_in.get().strip(),
                                               env, outp)
            if os.path.isfile(outp):
                self.log_line(f"wrote decompressed content -> {outp} ({os.path.getsize(outp):,} bytes)")
            else:
                self.log_line(f"(exit {rc}) no output produced - see log above")
        self._run_btn(p, "Dump Decompressed Zone", lambda: self._task("OAT dump zone", go))

    # -- tab: about ---------------------------------------------------------
    def _tab_about(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="About")
        p = self._card(f, f"{APP_TITLE}  {APP_VERSION}",
                       "Tools for Black Ops II (T6) Wii U fastfiles.")
        txt = (
            "Built-in (pure Python):\n"
            "   - Wii U fastfile decryptor / decompressor (Salsa20 + deflate, v148)\n"
            "   - Wii U fastfile repacker (v148 chunk framing + super-block alignment)\n"
            "   - structural zone validator (block policy, asset directory, script strings)\n\n"
            "Drives the extended OpenAssetTools Unlinker:\n"
            "   - big-endian v148 Wii U zone writer\n"
            "   - decompressed-zone dumper\n"
            "   - reads genuine Wii U fastfiles; signature-check bypass\n\n"
            "See README.md and USAGE.md for details and the full list of Wii U fixes."
        )
        ttk.Label(p, text=txt, style="Card.TLabel", justify="left",
                  font=("Consolas", 9)).pack(anchor="w")
        url = "https://github.com/tonytrawl/Wiiu_ff_studio"
        lr = ttk.Frame(p, style="Card.TFrame")
        lr.pack(anchor="w", pady=(16, 0))
        ttk.Label(lr, text="Project & source:  ", style="Card.TLabel").pack(side="left")
        link = tk.Label(lr, text="github.com/tonytrawl/Wiiu_ff_studio", bg=CARD, fg=ACCENT,
                        cursor="hand2", font=("Segoe UI", 10, "underline"))
        link.pack(side="left")
        link.bind("<Button-1>", lambda _e: webbrowser.open(url))


if __name__ == "__main__":
    Studio().mainloop()
