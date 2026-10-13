# -*- coding: utf-8 -*-
"""
KALKULATOR VALIDASI OMZET, OUTPUT, NILAI TAMBAH & RASIO  -  Sensus Ekonomi 2026

Rumus (Ringkasan Indikator):
    Omzet        = r27A
    Output       = r27A - r26C   (khusus Kategori G, Perdagangan)
                 = r27A          (kategori selain G)
    Nilai Tambah = Output - r26B - r26D
    Rasio        = Nilai Tambah / Output

Aturan validasi:
    1) Output harus positif (tidak minus / nol)
    2) Nilai Tambah tidak negatif
    3) Rasio NTB/Output berada dalam rentang threshold sesuai Kategori Usaha

Saran perubahan HANYA pada Omzet (r27A); semua pengeluaran dianggap tetap.

Penurunan saran:  Misal K = r26B + r26D.  Rasio = 1 - K / Output.
    Misal P = r26C untuk Kategori G, dan P = 0 untuk kategori lain.
    Rasio >= MIN  ->  Output >= K / (1 - MIN)
    Rasio <= MAX  ->  Output <= K / (1 - MAX)
    Omzet = Output + P   ->  rentang omzet valid = P + [K/(1-MIN) , K/(1-MAX)]

Kebutuhan: Python 3.8+ (hanya library bawaan, tidak perlu install apa pun).
"""

import math

EPS = 1e-12   # toleransi pembulatan floating point pada batas threshold

# --------------------------------------------------------------------------
# THRESHOLD RASIO NTB/OUTPUT MENURUT KATEGORI (dari materi)
# (huruf, uraian, MIN, MAX)  ->  None = tidak ada threshold
# --------------------------------------------------------------------------
KATEGORI = [
    ("A", "Pertanian, Kehutanan, dan Perikanan", 0.51, 0.94),
    ("B", "Pertambangan dan Penggalian", 0.28, 0.81),
    ("C", "Industri Pengolahan", 0.15, 0.61),
    ("D", "Pengadaan Listrik, Gas, Uap/Air Panas dan Udara Dingin", 0.13, 0.68),
    ("E", "Pengelolaan Air, Air Limbah, Sampah dan Daur Ulang", 0.29, 0.47),
    ("F", "Konstruksi", 0.34, 0.44),
    ("G", "Perdagangan Besar dan Eceran; Reparasi Kendaraan", 0.64, 0.78),
    ("H", "Pengangkutan dan Pergudangan", 0.29, 0.64),
    ("I", "Penyediaan Akomodasi dan Makan Minum", 0.36, 0.69),
    ("J", "Informasi dan Komunikasi", 0.36, 0.73),
    ("K", "Aktivitas Keuangan dan Asuransi", 0.50, 0.72),
    ("L", "Real Estat", 0.46, 0.86),
    ("M", "Aktivitas Profesional, Ilmiah dan Teknis", 0.50, 0.99),
    ("N", "Penyewaan, Ketenagakerjaan, Agen Perjalanan & Penunjang Usaha", 0.44, 0.57),
    ("O", "Administrasi Pemerintahan, Pertahanan, Jaminan Sosial", 0.54, 0.66),
    ("P", "Pendidikan", None, None),
    ("Q", "Aktivitas Kesehatan Manusia dan Aktivitas Sosial", 0.27, 0.82),
    ("R", "Kesenian, Hiburan dan Rekreasi", 0.20, 0.60),
    ("S", "Aktivitas Jasa Lainnya", 0.21, 0.57),
    ("T", "Aktivitas Rumah Tangga sebagai Pemberi Kerja", 0.30, 0.69),
    ("U", "Aktivitas Badan Internasional & Ekstra Internasional", None, None),
]
THRESHOLD = {k: (mn, mx) for k, _, mn, mx in KATEGORI}
KAT_NAMA = {k: n for k, n, _, _ in KATEGORI}


def kat_label(letter):
    return f"{letter} - {KAT_NAMA[letter]}"


# --------------------------------------------------------------------------
# FORMAT & PARSING ANGKA
# --------------------------------------------------------------------------
NUM_KEYS = ["a1", "b1", "a2", "b2", "r26a", "r26b", "r26c", "r26d", "r26e",
            "r27a", "r27b", "r27d"]
INT_KEYS = {"a1", "b1", "a2", "b2"}
LABELS = {
    "a1": "Pekerja laki-laki (a1)", "b1": "Pekerja perempuan (b1)",
    "a2": "Pekerja dibayar (a2)", "b2": "Pekerja tidak dibayar (b2)",
    "r26a": "26a Upah dan gaji", "r26b": "26b Biaya produksi",
    "r26c": "26c Biaya pembelian barang yang terjual",
    "r26d": "26d Biaya operasional", "r26e": "26e Biaya non-operasional",
    "r27a": "27a Nilai produksi/penjualan/pendapatan",
    "r27b": "27b Pendapatan lainnya", "r27d": "27d Persentase pendapatan online",
}


def parse_num(text):
    """Parse angka gaya Indonesia: 1.500.000 | 1500000 | 1.500.000,50 | Rp 2.000"""
    s = str(text).strip().replace("Rp", "").replace("rp", "").replace(" ", "")
    if s == "":
        return 0.0
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        if all(len(p) == 3 for p in parts[1:]) and 1 <= len(parts[0]) <= 3:
            s = s.replace(".", "")          # titik = pemisah ribuan
    val = float(s)                           # ValueError jika tidak valid
    if val < 0:
        raise ValueError("negatif")
    return val


def fmt(v):
    if v is None:
        return "-"
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v)):,}".replace(",", ".")
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_rp(v):
    return "Rp " + fmt(v) if v is not None else "-"


def fmt_ratio(v, nd=4):
    if v is None:
        return "-"
    return f"{v:.{nd}f}".replace(".", ",")


# --------------------------------------------------------------------------
# PERHITUNGAN & VALIDASI
# --------------------------------------------------------------------------
def pengurang_output(r):
    """Pengurang Output: r26C hanya dipakai untuk Kategori G; kategori lain = 0."""
    return r["r26c"] if r.get("kat", "") == "G" else 0


def evaluasi(r):
    """Hitung indikator dan periksa aturan untuk satu set isian."""
    out = r["r27a"] - pengurang_output(r)
    ntb = out - r["r26b"] - r["r26d"]
    rasio = ntb / out if out > 0 else None
    c1, c2 = r["a1"] + r["b1"], r["a2"] + r["b2"]
    kat = r.get("kat", "")
    tmin, tmax = THRESHOLD.get(kat, (None, None))

    cek = {}          # "pass" | "fail" | "na" (tidak ada threshold) | "pending"
    warns = []        # penjelasan pelanggaran
    notes = []        # catatan non-pelanggaran

    # 1. Output
    if out > 0:
        cek["output"] = "pass"
    else:
        cek["output"] = "fail"
        if r.get("kat", "") == "G":
            warns.append(f"Output {'MINUS' if out < 0 else 'bernilai 0'} ({fmt_rp(out)}): "
                         f"omzet r27A tidak lebih besar dari biaya pembelian barang terjual r26C "
                         f"(Output Kategori G = r27A − r26C).")
        else:
            warns.append(f"Output bernilai 0 ({fmt_rp(out)}): omzet/pendapatan r27A masih 0 "
                         f"(Output selain Kategori G = r27A).")

    # 2. Nilai tambah
    if ntb >= 0:
        cek["ntb"] = "pass"
    else:
        cek["ntb"] = "fail"
        warns.append(f"Nilai Tambah NEGATIF ({fmt_rp(ntb)}).")

    # 3. Rasio
    if not kat:
        cek["rasio"] = "pending"
        warns.append("Kategori usaha belum dipilih, threshold rasio belum bisa diperiksa.")
    elif tmin is None:
        cek["rasio"] = "na"
        notes.append(f"Kategori {kat} tidak memiliki threshold rasio (cek rasio dilewati).")
    elif rasio is None:
        cek["rasio"] = "fail"
        warns.append("Rasio tidak dapat dihitung karena Output ≤ 0.")
    elif rasio < tmin - EPS:
        cek["rasio"] = "fail"
        warns.append(f"Rasio {fmt_ratio(rasio)} DI BAWAH batas minimum {fmt_ratio(tmin, 2)}.")
    elif rasio > tmax + EPS:
        cek["rasio"] = "fail"
        warns.append(f"Rasio {fmt_ratio(rasio)} DI ATAS batas maksimum {fmt_ratio(tmax, 2)}.")
    else:
        cek["rasio"] = "pass"

    if kat and kat != "G" and r["r26c"] > 0:
        notes.append("Catatan: r26C tidak dipakai menghitung Output karena kategori selain G "
                     "(Output = r27A).")
    if c1 != c2:
        notes.append(f"Catatan: total pekerja c1 (a1+b1) = {fmt(c1)} berbeda dengan "
                     f"c2 (a2+b2) = {fmt(c2)}.")

    valid = all(v in ("pass", "na") for v in cek.values())
    return {"output": out, "ntb": ntb, "rasio": rasio, "c1": c1, "c2": c2,
            "f26": r["r26a"] + r["r26b"] + r["r26c"] + r["r26d"] + r["r26e"],
            "c27": r["r27a"] + r["r27b"],
            "tmin": tmin, "tmax": tmax, "cek": cek, "warns": warns, "notes": notes,
            "valid": valid}


def saran_omzet(r):
    """
    Saran omzet (r27A) agar Output > 0, NTB >= 0 dan rasio dalam threshold.
    Hanya omzet yang diubah; r26C, r26B, r26D dianggap tetap.
    """
    kat = r.get("kat", "")
    if not kat:
        return {"state": "nokat", "reason": "Pilih kategori usaha untuk mendapatkan saran."}

    c = pengurang_output(r)
    K = r["r26b"] + r["r26d"]
    tmin, tmax = THRESHOLD[kat]

    def ok_with(omzet):
        e = evaluasi(dict(r, r27a=omzet))
        return e["valid"]

    if tmin is None:                       # kategori P / U : cukup NTB >= 0 & Output > 0
        out_lo = math.ceil(K) if K > 0 else 1
        out_hi = None
    else:
        if K <= 0:
            return {"state": "infeasible",
                    "reason": ("Biaya produksi (r26B) + biaya operasional (r26D) = 0, sehingga rasio "
                               "selalu 1,0000 dan melebihi batas maksimum "
                               f"{fmt_ratio(tmax, 2)}. Tidak dapat diperbaiki hanya dengan mengubah omzet.")}
        out_lo = math.ceil(K / (1 - tmin) - 1e-6)
        out_hi = math.floor(K / (1 - tmax) + 1e-6)

    lo = c + out_lo
    hi = None if out_hi is None else c + out_hi

    # koreksi pembulatan di batas: pastikan batas bawah/atas benar-benar yang terdekat & valid
    for _ in range(5):
        if ok_with(lo):
            break
        lo += 1
    for _ in range(5):
        if lo - 1 > c and ok_with(lo - 1):
            lo -= 1
        else:
            break
    if hi is not None:
        for _ in range(5):
            if ok_with(hi):
                break
            hi -= 1
        for _ in range(5):
            if ok_with(hi + 1):
                hi += 1
            else:
                break
        if hi < lo or not ok_with(hi):
            return {"state": "infeasible",
                    "reason": "Tidak ada nilai omzet bulat yang memenuhi seluruh aturan "
                              "dengan pengeluaran saat ini."}

    cur = r["r27a"]
    if cur < lo:
        near = lo
    elif hi is not None and cur > hi:
        near = hi
    else:
        near = cur
    mid = None
    if hi is not None:
        mid = int(round((lo + hi) / 2))
        if not ok_with(mid):
            mid = None

    return {"state": "ok", "lo": lo, "hi": hi, "near": near, "mid": mid,
            "valid_now": ok_with(cur) and cur == near}


# --------------------------------------------------------------------------
# ANTARMUKA (TKINTER)
# --------------------------------------------------------------------------
def run_gui():
    import tkinter as tk
    from tkinter import ttk, messagebox

    C = {
        "bg": "#FFF7EC", "card": "#FFFFFF", "orange": "#F28C28", "orange_d": "#D9741A",
        "text": "#2B2B2B", "muted": "#7A7A7A", "line": "#F0DFC8", "sec": "#FFF1DC",
        "green": "#2E9E4F", "green_bg": "#E8F6EC", "red": "#C62828", "red_bg": "#FDECEC",
        "amber": "#9A6700", "amber_bg": "#FFF4D6", "blue": "#2F80C8", "blue_bg": "#E8F2FB",
        "grey_bg": "#F3F3F3",
    }
    FONT = "Segoe UI"

    root = tk.Tk()
    root.title("Kalkulator Validasi Omzet, Output, Nilai Tambah & Rasio — Sensus Ekonomi 2026")
    root.geometry("1360x790")
    root.minsize(1200, 720)
    root.configure(bg=C["bg"])

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    def make_button(parent, text, cmd, bg, fg="white", **kw):
        return tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=bg,
                         activeforeground=fg, relief="flat", bd=0, cursor="hand2",
                         font=(FONT, 10, "bold"), padx=12, pady=7, **kw)

    # ---------------- header ----------------
    header = tk.Frame(root, bg=C["orange"])
    header.pack(fill="x")
    tk.Label(header, text="KALKULATOR VALIDASI OMZET, OUTPUT, NILAI TAMBAH & RASIO",
             bg=C["orange"], fg="white", font=(FONT, 17, "bold")).pack(anchor="w", padx=22, pady=(12, 0))
    tk.Label(header, text="Sensus Ekonomi 2026  •  Output: Kategori G = r27A − r26C, selain G = r27A   |   "
                          "Nilai Tambah = Output − r26B − r26D   |   Rasio = NTB / Output",
             bg=C["orange"], fg="#FFF1DD", font=(FONT, 10)).pack(anchor="w", padx=22, pady=(0, 10))

    body = tk.Frame(root, bg=C["bg"])
    body.pack(fill="both", expand=True, padx=16, pady=12)
    body.columnconfigure(0, weight=0)
    body.columnconfigure(1, weight=1)
    body.rowconfigure(0, weight=1)

    # ================= PANEL KIRI : INPUT =================
    left = tk.Frame(body, bg=C["card"], highlightbackground=C["line"], highlightthickness=1)
    left.grid(row=0, column=0, sticky="ns", padx=(0, 12))
    tk.Label(left, text="Input Data Usaha", bg=C["card"], fg=C["text"],
             font=(FONT, 13, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 0))
    tk.Label(left, text="Kolom bertanda ● dipakai langsung dalam perhitungan indikator.",
             bg=C["card"], fg=C["muted"], font=(FONT, 8)).grid(row=1, column=0, columnspan=2,
                                                               sticky="w", padx=14)
    colA = tk.Frame(left, bg=C["card"])
    colB = tk.Frame(left, bg=C["card"])
    colA.grid(row=2, column=0, sticky="n", padx=(14, 7), pady=(0, 6))
    colB.grid(row=2, column=1, sticky="n", padx=(7, 14), pady=(0, 6))

    vars_, entries = {}, []

    def section(parent, title):
        tk.Label(parent, text=title, bg=C["sec"], fg=C["orange_d"], anchor="w",
                 font=(FONT, 9, "bold"), padx=8, pady=4).pack(fill="x", pady=(10, 4))

    def make_entry(parent, key, width=17):
        v = tk.StringVar()
        vars_[key] = v
        e = tk.Entry(parent, textvariable=v, font=(FONT, 10), relief="flat", width=width,
                     justify="right", highlightthickness=1, highlightbackground=C["line"],
                     highlightcolor=C["orange"], bg="#FFFDF9")
        entries.append(e)
        return e

    def input_row(parent, key, label, key_field=False):
        f = tk.Frame(parent, bg=C["card"])
        f.pack(fill="x", pady=2)
        tk.Label(f, text=("● " if key_field else "") + label, bg=C["card"],
                 fg=C["orange_d"] if key_field else C["text"],
                 font=(FONT, 9, "bold" if key_field else "normal"),
                 anchor="w", justify="left", wraplength=190).pack(side="left")
        make_entry(f, key).pack(side="right", ipady=3)

    def auto_row(parent, label):
        f = tk.Frame(parent, bg=C["card"])
        f.pack(fill="x", pady=(3, 0))
        tk.Label(f, text=label, bg=C["card"], fg=C["muted"], font=(FONT, 9, "bold"),
                 wraplength=190, justify="left").pack(side="left")
        l = tk.Label(f, text="0", bg=C["card"], fg=C["text"], font=(FONT, 10, "bold"))
        l.pack(side="right")
        return l

    # --- kolom A: kategori + r24 ---
    section(colA, "KATEGORI USAHA  (menentukan threshold)")
    vars_["kat"] = tk.StringVar()
    cb = ttk.Combobox(colA, textvariable=vars_["kat"], state="readonly", font=(FONT, 10),
                      values=[kat_label(k) for k, *_ in KATEGORI], width=34)
    cb.pack(fill="x", ipady=3)
    entries.append(cb)
    lbl_thr = tk.Label(colA, text="Threshold rasio: pilih kategori", bg=C["card"],
                       fg=C["muted"], font=(FONT, 9, "bold"))
    lbl_thr.pack(anchor="w", pady=(3, 0))

    section(colA, "24. PEKERJA (orang)")
    input_row(colA, "a1", "a1. Pekerja laki-laki")
    input_row(colA, "b1", "b1. Pekerja perempuan")
    input_row(colA, "a2", "a2. Pekerja dibayar")
    input_row(colA, "b2", "b2. Pekerja tidak dibayar")
    lbl_c1 = auto_row(colA, "c1. Total (a1+b1)")
    lbl_c2 = auto_row(colA, "c2. Total (a2+b2)")

    # --- kolom B: r26 ---
    section(colB, "26. RINCIAN PENGELUARAN 2025 (Rp)")
    input_row(colB, "r26a", "a. Upah dan gaji, serta jaminan sosial pegawai  [r26A]")
    input_row(colB, "r26b", "b. Biaya produksi  [r26B]", key_field=True)
    input_row(colB, "r26c", "c. Biaya pembelian barang yang terjual (khusus perdagangan)  [r26C]  — dipakai untuk Output hanya jika Kategori G", key_field=True)
    input_row(colB, "r26d", "d. Biaya operasional  [r26D]", key_field=True)
    input_row(colB, "r26e", "e. Biaya non-operasional")
    lbl_f26 = auto_row(colB, "f. Total pengeluaran (a+b+c+d+e)")

    # --- kolom A: r27 ---
    section(colA, "27. NILAI PRODUKSI/PENJUALAN/PENDAPATAN 2025 (Rp)")
    input_row(colA, "r27a", "a. Nilai produksi/penjualan/ pendapatan barang & jasa  [r27A = Omzet]", key_field=True)
    input_row(colA, "r27b", "b. Pendapatan lainnya")
    lbl_c27 = auto_row(colA, "c. Total (a+b)")
    input_row(colA, "r27d", "d. Persentase pendapatan online (%)")

    btns = tk.Frame(left, bg=C["card"])
    btns.grid(row=3, column=0, columnspan=2, sticky="ew", padx=14, pady=(4, 14))
    make_button(btns, "⟲  Kosongkan Semua Isian", lambda: clear_form(), C["red"]).pack(fill="x")

    # ================= PANEL KANAN : HASIL =================
    right = tk.Frame(body, bg=C["bg"])
    right.grid(row=0, column=1, sticky="nsew")
    right.columnconfigure(0, weight=1)

    # --- banner status ---
    banner = tk.Label(right, text="", font=(FONT, 15, "bold"), anchor="w", padx=16, pady=12)
    banner.grid(row=0, column=0, sticky="ew", pady=(0, 10))

    # --- metrik ---
    mcard = tk.Frame(right, bg=C["card"], highlightbackground=C["line"], highlightthickness=1)
    mcard.grid(row=1, column=0, sticky="ew", pady=(0, 10))
    metric, metric_title = {}, {}
    for i, (key, title) in enumerate([
        ("omzet", "Omzet (r27A)"), ("output", "Output"),
        ("ntb", "Nilai Tambah"), ("rasio", "Rasio NTB/Output"), ("thr", "Threshold (MIN – MAX)"),
    ]):
        mcard.columnconfigure(i, weight=1)
        f = tk.Frame(mcard, bg=C["card"])
        f.grid(row=0, column=i, sticky="ew", padx=12, pady=10)
        tl = tk.Label(f, text=title, bg=C["card"], fg=C["muted"], font=(FONT, 9))
        tl.pack(anchor="w")
        metric_title[key] = tl
        l = tk.Label(f, text="-", bg=C["card"], fg=C["text"], font=(FONT, 14, "bold"))
        l.pack(anchor="w")
        metric[key] = l

    # --- daftar pengecekan ---
    ccard = tk.Frame(right, bg=C["card"], highlightbackground=C["line"], highlightthickness=1)
    ccard.grid(row=2, column=0, sticky="ew", pady=(0, 10))
    tk.Label(ccard, text="PENGECEKAN ATURAN", bg=C["card"], fg=C["orange_d"],
             font=(FONT, 9, "bold")).pack(anchor="w", padx=14, pady=(8, 2))
    check_rows = {}
    for key, title in (("output", "Output positif (tidak minus / nol)"),
                       ("ntb", "Nilai Tambah tidak negatif"),
                       ("rasio", "Rasio NTB/Output masuk rentang threshold")):
        f = tk.Frame(ccard, bg=C["card"])
        f.pack(fill="x", padx=14, pady=1)
        icon = tk.Label(f, text="•", bg=C["card"], fg=C["muted"], font=(FONT, 12, "bold"), width=2)
        icon.pack(side="left")
        tk.Label(f, text=title, bg=C["card"], fg=C["text"], font=(FONT, 10)).pack(side="left")
        det = tk.Label(f, text="", bg=C["card"], fg=C["muted"], font=(FONT, 9))
        det.pack(side="right")
        check_rows[key] = (icon, det)
    msg = tk.Label(ccard, text="", bg=C["card"], fg=C["red"], font=(FONT, 9), anchor="w",
                   justify="left", wraplength=780)
    msg.pack(fill="x", padx=14, pady=(6, 10))

    # --- saran omzet ---
    scard = tk.Frame(right, bg=C["blue_bg"], highlightbackground="#BBD7F0", highlightthickness=1)
    scard.grid(row=3, column=0, sticky="ew", pady=(0, 10))
    tk.Label(scard, text="SARAN NILAI OMZET (r27A)  —  hanya omzet yang diubah, pengeluaran tetap",
             bg=C["blue_bg"], fg=C["blue"], font=(FONT, 9, "bold")).pack(anchor="w", padx=14, pady=(8, 2))
    lbl_range = tk.Label(scard, text="", bg=C["blue_bg"], fg=C["text"], font=(FONT, 10),
                         anchor="w", justify="left")
    lbl_range.pack(fill="x", padx=14, pady=(2, 0))
    lbl_near = tk.Label(scard, text="", bg=C["blue_bg"], fg=C["blue"], font=(FONT, 16, "bold"),
                        anchor="w", justify="left")
    lbl_near.pack(fill="x", padx=14, pady=(4, 0))
    lbl_near_d = tk.Label(scard, text="", bg=C["blue_bg"], fg=C["text"], font=(FONT, 9),
                          anchor="w", justify="left", wraplength=780)
    lbl_near_d.pack(fill="x", padx=14)
    lbl_mid = tk.Label(scard, text="", bg=C["blue_bg"], fg=C["text"], font=(FONT, 9),
                       anchor="w", justify="left", wraplength=780)
    lbl_mid.pack(fill="x", padx=14, pady=(4, 0))
    sbar = tk.Frame(scard, bg=C["blue_bg"])
    sbar.pack(fill="x", padx=14, pady=(8, 10))
    btn_near = make_button(sbar, "✔  Pakai Saran Omzet", lambda: apply_omzet("near"), C["blue"])
    btn_near.pack(side="left")
    btn_mid = make_button(sbar, "Pakai Nilai Tengah Rentang", lambda: apply_omzet("mid"), "#6FA8DC")
    btn_mid.pack(side="left", padx=8)

    # --- tombol bawah ---
    bar = tk.Frame(right, bg=C["bg"])
    bar.grid(row=4, column=0, sticky="ew")
    make_button(bar, "📋  Salin Hasil", lambda: copy_result(), "#8D8D8D").pack(side="left")
    foot = tk.Label(bar, text="", bg=C["bg"], fg=C["muted"], font=(FONT, 9))
    foot.pack(side="left", padx=12)

    state = {"saran": None, "ev": None, "rec": None}

    # ---------------- fungsi ----------------
    def get_values():
        vals, errors = {}, []
        for key in NUM_KEYS:
            try:
                v = parse_num(vars_[key].get())
                if key in INT_KEYS and abs(v - round(v)) > 1e-9:
                    raise ValueError("int")
                if key == "r27d" and v > 100:
                    raise ValueError("pct")
            except ValueError:
                extra = (" (bilangan bulat)" if key in INT_KEYS else
                         " (0 – 100)" if key == "r27d" else "")
                errors.append(f"'{LABELS[key]}' tidak valid — gunakan angka tidak negatif{extra}.")
                v = 0.0
            vals[key] = v
        k = vars_["kat"].get().strip()
        vals["kat"] = k[0] if k else ""
        return vals, errors

    def form_empty():
        for k in NUM_KEYS:
            if vars_[k].get().strip():
                return False
        return not vars_["kat"].get()

    def set_banner(level, text):
        col = {"ok": (C["green_bg"], C["green"]), "bad": (C["red_bg"], C["red"]),
               "idle": (C["grey_bg"], C["muted"]), "warn": (C["amber_bg"], C["amber"])}[level]
        banner.config(text=text, bg=col[0], fg=col[1])

    def refresh(*_):
        rec, errors = get_values()
        ev = evaluasi(rec)
        state["rec"], state["ev"] = rec, ev

        k = vars_["kat"].get().strip()
        if k:
            mn, mx = THRESHOLD[k[0]]
            lbl_thr.config(text=(f"Threshold rasio: {fmt_ratio(mn, 2)} – {fmt_ratio(mx, 2)}"
                                 if mn is not None else "Kategori ini tidak memiliki threshold rasio"))
        else:
            lbl_thr.config(text="Threshold rasio: pilih kategori")

        lbl_c1.config(text=fmt(ev["c1"]))
        lbl_c2.config(text=fmt(ev["c2"]), fg=C["red"] if ev["c1"] != ev["c2"] else C["text"])
        lbl_f26.config(text=fmt(ev["f26"]))
        lbl_c27.config(text=fmt(ev["c27"]))

        metric_title["output"].config(
            text=("Output (r27A − r26C)  • Kategori G" if rec["kat"] == "G"
                  else "Output (= r27A)  • selain G" if rec["kat"] else "Output"))
        metric["omzet"].config(text=fmt(rec["r27a"]))
        metric["output"].config(text=fmt(ev["output"]),
                                fg=C["red"] if ev["cek"]["output"] == "fail" else C["text"])
        metric["ntb"].config(text=fmt(ev["ntb"]),
                             fg=C["red"] if ev["cek"]["ntb"] == "fail" else C["green"])
        metric["rasio"].config(text=fmt_ratio(ev["rasio"]),
                               fg=C["red"] if ev["cek"]["rasio"] == "fail" else C["text"])
        metric["thr"].config(text=(f"{fmt_ratio(ev['tmin'], 2)} – {fmt_ratio(ev['tmax'], 2)}"
                                   if ev["tmin"] is not None else "-"))

        # daftar cek
        sym = {"pass": ("✔", C["green"]), "fail": ("✖", C["red"]),
               "na": ("ⓘ", C["muted"]), "pending": ("?", C["amber"])}
        det_txt = {
            "output": fmt_rp(ev["output"]),
            "ntb": fmt_rp(ev["ntb"]),
            "rasio": (f"{fmt_ratio(ev['rasio'])}  (batas {fmt_ratio(ev['tmin'], 2)} – {fmt_ratio(ev['tmax'], 2)})"
                      if ev["tmin"] is not None and ev["rasio"] is not None
                      else "tanpa threshold" if ev["cek"]["rasio"] == "na" else "-"),
        }
        idle = form_empty()
        for key, (icon, det) in check_rows.items():
            if idle:
                icon.config(text="•", fg=C["muted"])
                det.config(text="")
            else:
                s, colr = sym[ev["cek"][key]]
                icon.config(text=s, fg=colr)
                det.config(text=det_txt[key], fg=colr if s in ("✖",) else C["muted"])

        lines = []
        if errors:
            lines += ["⛔ " + e for e in errors]
        if not idle:
            lines += ["⚠ " + w for w in ev["warns"]]
            lines += ["ℹ " + n for n in ev["notes"]]
        msg.config(text="\n".join(lines), fg=C["red"] if (errors or ev["warns"]) and not idle else C["muted"])

        # banner
        if idle:
            set_banner("idle", "Isi data usaha di sebelah kiri untuk memulai validasi.")
        elif errors:
            set_banner("warn", "⚠  Ada isian yang tidak valid — perbaiki terlebih dahulu")
        elif not rec["kat"]:
            set_banner("warn", "⚠  Pilih Kategori Usaha agar threshold dapat diperiksa")
        elif ev["valid"]:
            set_banner("ok", "✔  SESUAI ATURAN — Output, Nilai Tambah dan Rasio memenuhi syarat")
        else:
            n_bad = sum(1 for v in ev["cek"].values() if v == "fail")
            set_banner("bad", f"✖  TIDAK SESUAI ATURAN — {n_bad} pengecekan tidak terpenuhi")

        refresh_saran(rec, ev, idle or bool(errors))

    def refresh_saran(rec, ev, idle):
        sar = saran_omzet(rec) if not idle else None
        state["saran"] = sar
        btn_near.config(state="disabled")
        btn_mid.config(state="disabled")
        lbl_range.config(text="")
        lbl_near.config(text="")
        lbl_near_d.config(text="")
        lbl_mid.config(text="")
        if sar is None:
            lbl_near.config(text="—", fg=C["muted"])
            lbl_near_d.config(text="Saran akan muncul setelah data diisi.")
            return
        if sar["state"] in ("nokat", "infeasible"):
            lbl_near.config(text="Saran tidak tersedia", fg=C["muted"])
            lbl_near_d.config(text=sar["reason"])
            return

        lo, hi, near, mid = sar["lo"], sar["hi"], sar["near"], sar["mid"]
        if hi is not None:
            lbl_range.config(text=f"Rentang omzet yang memenuhi aturan:  {fmt_rp(lo)}  s.d.  {fmt_rp(hi)}")
        else:
            lbl_range.config(text=f"Omzet minimum agar Output positif dan NTB tidak negatif:  {fmt_rp(lo)}"
                                  "  (tanpa batas atas — kategori tanpa threshold)")

        cur = rec["r27a"]
        if ev["valid"] and near == cur:
            lbl_near.config(text="Omzet saat ini sudah sesuai aturan", fg=C["green"])
            lbl_near_d.config(text="Tidak perlu perubahan omzet.")
        else:
            e2 = evaluasi(dict(rec, r27a=near))
            diff = near - cur
            arah = "naik" if diff > 0 else "turun"
            pct = f" ({abs(diff) / cur * 100:.1f}%)" if cur > 0 else ""
            lbl_near.config(text=f"Saran omzet: {fmt_rp(near)}", fg=C["blue"])
            lbl_near_d.config(text=(f"Perubahan paling kecil dari omzet saat ini: {arah} {fmt_rp(abs(diff))}{pct}.\n"
                                    f"Hasilnya → Output {fmt_rp(e2['output'])}  |  NTB {fmt_rp(e2['ntb'])}  |  "
                                    f"Rasio {fmt_ratio(e2['rasio'])}"))
            btn_near.config(state="normal")
        if mid is not None and mid != near:
            e3 = evaluasi(dict(rec, r27a=mid))
            lbl_mid.config(text=(f"Alternatif (tengah rentang): {fmt_rp(mid)}  →  "
                                 f"NTB {fmt_rp(e3['ntb'])}, Rasio {fmt_ratio(e3['rasio'])}"))
            btn_mid.config(state="normal")

    def apply_omzet(which):
        sar = state["saran"]
        if not sar or sar.get("state") != "ok":
            return
        val = sar["near"] if which == "near" else sar["mid"]
        if val is None:
            return
        vars_["r27a"].set(str(int(val)))
        foot.config(text=f"Omzet (r27A) diubah menjadi {fmt_rp(val)}.")

    def clear_form():
        for v in vars_.values():
            v.set("")
        foot.config(text="Semua isian dikosongkan — siap input baru.")
        entries[0].focus_set()

    def copy_result():
        ev, rec, sar = state["ev"], state["rec"], state["saran"]
        if ev is None or form_empty():
            messagebox.showinfo("Salin hasil", "Belum ada data untuk disalin.")
            return
        kat = rec["kat"]
        lines = [
            f"Kategori: {kat_label(kat) if kat else '-'}",
            f"Omzet (r27A): {fmt_rp(rec['r27a'])}",
            f"Output: {fmt_rp(ev['output'])}",
            f"Nilai Tambah: {fmt_rp(ev['ntb'])}",
            f"Rasio NTB/Output: {fmt_ratio(ev['rasio'])}"
            + (f" (threshold {fmt_ratio(ev['tmin'], 2)} – {fmt_ratio(ev['tmax'], 2)})"
               if ev["tmin"] is not None else ""),
            "Status: " + ("SESUAI ATURAN" if ev["valid"] else "TIDAK SESUAI ATURAN"),
        ]
        lines += ["- " + w for w in ev["warns"]]
        if sar and sar.get("state") == "ok" and not (ev["valid"] and sar["near"] == rec["r27a"]):
            lines.append(f"Saran omzet: {fmt_rp(sar['near'])}"
                         + (f" (rentang valid {fmt_rp(sar['lo'])} s.d. {fmt_rp(sar['hi'])})"
                            if sar["hi"] is not None else f" (minimum {fmt_rp(sar['lo'])})"))
        root.clipboard_clear()
        root.clipboard_append("\n".join(lines))
        foot.config(text="Hasil disalin ke clipboard.")

    for v in vars_.values():
        v.trace_add("write", refresh)
    for i, e in enumerate(entries):
        def nxt(ev, i=i):
            entries[(i + 1) % len(entries)].focus_set()
            return "break"
        e.bind("<Return>", nxt)

    refresh()
    entries[0].focus_set()
    root.mainloop()


if __name__ == "__main__":
    run_gui()
