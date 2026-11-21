"""
Video/Audio Converter
Download video's (MP4) en audio (MP3) van YouTube en 1000+ andere websites.

Gebruikt op de achtergrond:
  - yt-dlp   (downloader: YouTube, Vimeo, TikTok, Instagram, X, Facebook, SoundCloud, ...)
  - ffmpeg   (samenvoegen van beeld+geluid en omzetten naar MP3)
  - deno     (JavaScript-runtime die yt-dlp nodig heeft voor YouTube)

Deze hulpprogramma's worden bij de eerste start automatisch gedownload naar
%LOCALAPPDATA%\\VideoAudioConverter\\bin
"""

import itertools
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

APP_NAME = "Video/Audio Converter"
APP_VERSION = "2.3.0"   # wordt bij een release automatisch gezet vanuit de git-tag

# GitHub-repository waar nieuwe versies (Releases) van dit programma staan.
# Moet een openbare repository zijn. Leeg laten = niet controleren op updates.
UPDATE_REPO = "basbas011/Video-Audio-Converter"
SETUP_ASSET = "Video-Audio-Converter-Setup.exe"

IS_WIN = os.name == "nt"
EXE = ".exe" if IS_WIN else ""
BASE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "VideoAudioConverter")
BIN_DIR = os.environ.get("VAC_BIN_DIR") or os.path.join(BASE_DIR, "bin")
SETTINGS_FILE = os.path.join(BASE_DIR, "instellingen.json")

YTDLP_EXE = os.path.join(BIN_DIR, "yt-dlp" + EXE)
FFMPEG_EXE = os.path.join(BIN_DIR, "ffmpeg" + EXE)
DENO_EXE = os.path.join(BIN_DIR, "deno" + EXE)

# nightly: krijgt YouTube-fixes vaak dagen eerder dan de stabiele versie
YTDLP_URL = "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp.exe"
FFMPEG_URL = "https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip"
DENO_URL = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"

CREATE_NO_WINDOW = 0x08000000 if IS_WIN else 0

VIDEO_QUALITIES = {
    "Beste kwaliteit": None,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
    "360p": 360,
}
AUDIO_QUALITIES = {
    "320 kbps": "320K",
    "256 kbps": "256K",
    "192 kbps": "192K",
    "128 kbps": "128K",
}

# Kleuren (licht, donker)
ACCENT = ("#DC2626", "#EF4444")
ACCENT_HOVER = ("#B91C1C", "#DC2626")
GREEN = ("#16A34A", "#22C55E")
RED = ("#DC2626", "#F87171")
BLUE = ("#2563EB", "#60A5FA")
MUTED = ("#6B7280", "#9CA3AF")
CARD = ("#FFFFFF", "#1F2023")
BG = ("#F3F4F6", "#141517")
ROW = ("#F9FAFB", "#26272B")
TEXT = ("#111827", "#F3F4F6")
SEG = dict(fg_color=("#E5E7EB", "#2A2B30"), unselected_color=("#E5E7EB", "#2A2B30"),
           unselected_hover_color=("#D1D5DB", "#34353B"), selected_color=("#FFFFFF", "#4B4C55"),
           selected_hover_color=("#FFFFFF", "#4B4C55"), text_color=TEXT, height=30, corner_radius=8)
BORDER = ("#E5E7EB", "#33343A")

# Tijdelijk naamstuk voor MP3's, zodat yt-dlp een bestaande MP4 met dezelfde naam
# niet als bronbestand gebruikt (en verwijdert). Na afloop wordt het weggehaald.
AUDIO_TAG = ".vac-audio"

PROGRESS_RE = re.compile(r"^PROGRESS\s+([\d.]+)%\|([^|]*)\|(.*)$")

FRIENDLY_ERRORS = [
    ("Video unavailable", "Video niet beschikbaar"),
    ("Private video", "Privévideo"),
    ("Sign in to confirm your age", "Leeftijdsbeperking: inloggen vereist"),
    ("Sign in to confirm you", "YouTube vraagt om in te loggen. Probeer later opnieuw"),
    ("members-only", "Alleen voor kanaalleden"),
    ("Unsupported URL", "Deze link of website wordt niet ondersteund"),
    ("is not a valid URL", "Dit is geen geldige link"),
    ("HTTP Error 403", "YouTube weigert de download (403), ook na een nieuwe poging. Probeer het later opnieuw"),
    ("HTTP Error 404", "Niet gevonden (404)"),
    ("HTTP Error 429", "Te veel verzoeken. Probeer het later opnieuw"),
    ("Unable to download webpage", "Kan de website niet bereiken"),
    ("Requested format is not available", "Gekozen kwaliteit niet beschikbaar"),
    ("This live event will begin", "Livestream is nog niet begonnen"),
    ("No space left", "Schijf is vol"),
]

STATUS_STYLE = {
    "ophalen": ("…", BLUE, "Playlist ophalen…"),
    "wachten": ("•", MUTED, "In de wachtrij"),
    "bezig": ("↓", BLUE, "Starten…"),
    "gereed": ("✓", GREEN, "Gereed"),
    "mislukt": ("✕", RED, "Mislukt"),
    "gestopt": ("■", MUTED, "Gestopt"),
}


# --------------------------------------------------------------------------- #
#  Instellingen
# --------------------------------------------------------------------------- #

def load_settings():
    s = {"outdir": os.path.join(os.path.expanduser("~"), "Downloads"), "parallel": 3,
         "mode": "MP4", "playlist": "Alleen deze video", "vq": "Beste kwaliteit", "aq": "192 kbps"}
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            s.update(json.load(f))
    except (OSError, ValueError):
        pass
    if not os.path.isdir(s["outdir"]):
        s["outdir"] = os.path.join(os.path.expanduser("~"), "Downloads")
    return s


def save_settings(s):
    try:
        os.makedirs(BASE_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
#  Updates van het programma zelf (via GitHub Releases)
# --------------------------------------------------------------------------- #

def parse_version(text):
    nums = [int(n) for n in re.findall(r"\d+", text or "")[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def check_app_update():
    """Geeft (versie, download-url) terug als er een nieuwere release is, anders None."""
    if not UPDATE_REPO:
        return None
    api = os.environ.get("VAC_UPDATE_API") or f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
    req = urllib.request.Request(api, headers={"User-Agent": "VideoAudioConverter/" + APP_VERSION,
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    tag = data.get("tag_name", "")
    if parse_version(tag) <= parse_version(APP_VERSION):
        return None
    for asset in data.get("assets", []):
        if asset.get("name") == SETUP_ASSET:
            return tag.lstrip("vV"), asset["browser_download_url"]
    return None


# --------------------------------------------------------------------------- #
#  Hulpprogramma's downloaden
# --------------------------------------------------------------------------- #

def download_file(url, dest, report):
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "VideoAudioConverter/" + APP_VERSION})
    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            report(done / total if total else None, f"{done / 1048576:.0f} MB")
    os.replace(tmp, dest)


def extract_from_zip(zip_path, wanted_names):
    with zipfile.ZipFile(zip_path) as z:
        for member in z.namelist():
            name = os.path.basename(member)
            if name.lower() in wanted_names:
                with z.open(member) as src, open(os.path.join(BIN_DIR, name), "wb") as dst:
                    shutil.copyfileobj(src, dst)


def tools_missing():
    return [p for p in (YTDLP_EXE, FFMPEG_EXE, DENO_EXE) if not os.path.isfile(p)]


def install_tools(report):
    os.makedirs(BIN_DIR, exist_ok=True)
    if not os.path.isfile(YTDLP_EXE):
        download_file(YTDLP_URL, YTDLP_EXE, lambda p, t: report(p, "Downloader ophalen… " + t))
    if not os.path.isfile(DENO_EXE):
        zip_path = os.path.join(BIN_DIR, "deno.zip")
        download_file(DENO_URL, zip_path, lambda p, t: report(p, "YouTube-ondersteuning ophalen… " + t))
        extract_from_zip(zip_path, {"deno.exe"})
        os.remove(zip_path)
    if not os.path.isfile(FFMPEG_EXE):
        zip_path = os.path.join(BIN_DIR, "ffmpeg.zip")
        download_file(FFMPEG_URL, zip_path, lambda p, t: report(p, "Converter (FFmpeg) ophalen… " + t))
        report(None, "FFmpeg uitpakken…")
        extract_from_zip(zip_path, {"ffmpeg.exe", "ffprobe.exe"})
        os.remove(zip_path)


# --------------------------------------------------------------------------- #
#  yt-dlp
# --------------------------------------------------------------------------- #

def base_args():
    return [
        YTDLP_EXE, "--newline", "--no-colors", "--encoding", "utf-8",
        "--ffmpeg-location", BIN_DIR,
        "--js-runtimes", f"deno:{DENO_EXE}",
    ]


def build_download_command(job):
    cmd = base_args() + [
        "--paths", job.outdir,
        "--paths", "temp:" + os.path.join(BASE_DIR, "tmp"),
        "--output", "%(title).150B" + (AUDIO_TAG if job.mode == "MP3" else "") + ".%(ext)s",
        "--windows-filenames", "--no-mtime", "--embed-metadata", "--no-playlist",
        "--progress", "--no-simulate",
        "--progress-template",
        "download:PROGRESS %(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
        "--print", "before_dl:TITLE %(title)s",
        "--print", "after_move:FILE %(filepath)s",
    ]
    if job.mode == "MP3":
        cmd += ["--format", "bestaudio/best", "--extract-audio", "--audio-format", "mp3",
                "--audio-quality", AUDIO_QUALITIES[job.quality], "--embed-thumbnail"]
    else:
        height = VIDEO_QUALITIES[job.quality]
        res = f"res:{height}" if height else "res"
        cmd += ["--format", "bv*+ba/b",
                # voorkeur voor H.264 + AAC zodat de MP4 overal afspeelt
                "--format-sort", f"{res},vcodec:h264,acodec:m4a",
                "--merge-output-format", "mp4", "--remux-video", "mp4"]
    cmd.append(job.url)
    return cmd


def build_playlist_command(url):
    return base_args() + ["--flat-playlist", "--yes-playlist", "--ignore-errors",
                          "--print", "%(webpage_url,url)s\t%(title,id)s", url]


def popen(cmd):
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace",
                            creationflags=CREATE_NO_WINDOW, cwd=BIN_DIR if os.path.isdir(BIN_DIR) else None)


def kill_tree(proc):
    if proc and proc.poll() is None:
        if IS_WIN:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           creationflags=CREATE_NO_WINDOW, capture_output=True)
        else:
            proc.kill()


def friendly_error(msg):
    for needle, nl in FRIENDLY_ERRORS:
        if needle.lower() in msg.lower():
            return nl
    msg = re.sub(r"^\[[^\]]+\]\s*[\w-]+:\s*", "", msg).strip()
    return (msg[:140] + "…") if len(msg) > 140 else (msg or "Onbekende fout")


def shorten(text, n=80):
    return text if len(text) <= n else text[: n - 1] + "…"


# --------------------------------------------------------------------------- #
#  Download-taak
# --------------------------------------------------------------------------- #

_ids = itertools.count(1)


class Job:
    def __init__(self, url, mode, quality, outdir, title=None, expand=False):
        self.id = next(_ids)
        self.url = url
        self.mode = mode
        self.quality = quality
        self.outdir = outdir
        self.title = title
        self.expand = expand
        self.state = "ophalen" if expand else "wachten"
        self.percent = 0.0
        self.detail = ""
        self.error = ""
        self.filepath = None
        self.proc = None
        self.cancelled = False
        self.retried = False
        self.row = None

    @property
    def label(self):
        return self.title or self.url

    @property
    def badge(self):
        q = self.quality.replace(" kbps", "k").replace("Beste kwaliteit", "Beste")
        return f"{self.mode} · {q}"


class JobRow(ctk.CTkFrame):
    def __init__(self, master, job, app):
        super().__init__(master, fg_color=ROW, corner_radius=10, border_width=1, border_color=BORDER)
        self.job, self.app = job, app
        self.grid_columnconfigure(1, weight=1)

        self.icon_bg = ctk.CTkFrame(self, width=34, height=34, corner_radius=17)
        self.icon_bg.grid(row=0, column=0, rowspan=2, padx=(12, 10), pady=10)
        self.icon_bg.grid_propagate(False)
        self.icon = ctk.CTkLabel(self.icon_bg, text="", width=20, height=20, fg_color="transparent",
                                 font=ctk.CTkFont(size=15, weight="bold"), text_color="white")
        self.icon.place(relx=0.5, rely=0.5, anchor="center")

        self.title = ctk.CTkLabel(self, text="", anchor="w", font=ctk.CTkFont(size=13, weight="bold"))
        self.title.grid(row=0, column=1, sticky="ew", pady=(10, 0))

        sub = ctk.CTkFrame(self, fg_color="transparent")
        sub.grid(row=1, column=1, sticky="ew", pady=(0, 10))
        sub.grid_columnconfigure(1, weight=1)
        self.badge = ctk.CTkLabel(sub, text=job.badge, font=ctk.CTkFont(size=11), text_color=MUTED,
                                  fg_color=BORDER, corner_radius=6, height=20, padx=8)
        self.badge.grid(row=0, column=0, padx=(0, 8))
        self.status = ctk.CTkLabel(sub, text="", anchor="w", font=ctk.CTkFont(size=12), height=20)
        self.status.grid(row=0, column=1, sticky="ew")
        self.bar = ctk.CTkProgressBar(sub, height=6, progress_color=BLUE, fg_color=BORDER)
        self.bar.set(0)

        self.action = ctk.CTkButton(self, text="", width=84, height=30, corner_radius=8,
                                    fg_color="transparent", border_width=1, border_color=BORDER,
                                    text_color=("#111827", "#E5E7EB"), hover_color=BORDER,
                                    command=self.on_action)
        self.action.grid(row=0, column=2, rowspan=2, padx=(12, 4))
        self.remove = ctk.CTkButton(self, text="✕", width=30, height=30, corner_radius=8,
                                    fg_color="transparent", text_color=MUTED, hover_color=("#FEE2E2", "#3B1F22"),
                                    font=ctk.CTkFont(size=14), command=lambda: app.remove_job(job))
        self.remove.grid(row=0, column=3, rowspan=2, padx=(0, 10))
        self._last = None
        self.refresh()

    def on_action(self):
        j = self.job
        if j.state in ("bezig", "wachten", "ophalen"):
            self.app.cancel_job(j)
        elif j.state in ("mislukt", "gestopt"):
            self.app.retry_job(j)
        elif j.state == "gereed":
            self.app.show_file(j)

    def refresh(self):
        j = self.job
        key = (j.state, round(j.percent, 1), j.detail, j.title, j.error)
        if key == self._last:
            return
        self._last = key
        sym, color, default = STATUS_STYLE[j.state]
        self.icon_bg.configure(fg_color=color)
        self.icon.configure(text=sym)
        self.title.configure(text=shorten(j.label, 90))

        if j.state == "bezig":
            text = j.detail or default
            self.bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
            self.bar.set(j.percent / 100)
            self.status.configure(text=text, text_color=("#374151", "#D1D5DB"))
        else:
            self.bar.grid_forget()
            if j.state == "mislukt":
                self.status.configure(text=j.error or default, text_color=RED)
            elif j.state == "gereed":
                self.status.configure(text="Gereed" + (f" · {os.path.basename(j.filepath)}" if j.filepath else ""),
                                      text_color=GREEN)
            elif j.state == "wachten" and j.detail:
                self.status.configure(text=j.detail, text_color=("#B45309", "#FBBF24"))
            else:
                self.status.configure(text=default, text_color=MUTED)

        self.action.configure(text={"bezig": "Stoppen", "wachten": "Annuleren", "ophalen": "Annuleren",
                                    "mislukt": "Opnieuw", "gestopt": "Opnieuw", "gereed": "Tonen"}[j.state])


# --------------------------------------------------------------------------- #
#  Hoofdvenster
# --------------------------------------------------------------------------- #

class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        self.settings = load_settings()
        self.events = queue.Queue()
        self.jobs = []
        self.ready = not tools_missing()
        self.updating = False
        self.update_silent = False
        self.retry_at = {}

        self.title(APP_NAME)
        self.geometry("920x820")
        self.minsize(780, 640)
        self._set_icon()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_input()
        self._build_list()
        self._build_footer()
        self.update_summary()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.tick)
        if not self.ready:
            self.after(300, self.install)
        else:
            # bij elke start stil de nieuwste downloader ophalen
            self.after(400, lambda: self.update_ytdlp(silent=True))
        self.after(1500, self.start_app_update_check)

    # ---- opbouw ---------------------------------------------------------- #
    def _set_icon(self):
        icon = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "icon.ico")
        if IS_WIN and os.path.isfile(icon):
            # customtkinter zet zelf na ~200 ms een icoon; daarna overschrijven
            self.after(250, lambda: self.iconbitmap(icon))

    def _build_header(self):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))
        logo = ctk.CTkLabel(head, text="▶", width=40, height=40, corner_radius=10, fg_color=ACCENT,
                            text_color="white", font=ctk.CTkFont(size=18))
        logo.pack(side="left")
        txt = ctk.CTkFrame(head, fg_color="transparent")
        txt.pack(side="left", padx=12)
        ctk.CTkLabel(txt, text=APP_NAME, font=ctk.CTkFont(size=20, weight="bold"), anchor="w").pack(anchor="w")
        ctk.CTkLabel(txt, text="YouTube, Vimeo, TikTok, Instagram, SoundCloud en 1000+ andere sites",
                     font=ctk.CTkFont(size=12), text_color=MUTED, anchor="w").pack(anchor="w")

        # Melding "nieuwe versie" (verschijnt alleen als er een update is)
        self.upd = ctk.CTkFrame(head, fg_color=("#EFF6FF", "#172033"), corner_radius=10,
                                border_width=1, border_color=("#BFDBFE", "#1E3A5F"))
        self.upd_lbl = ctk.CTkLabel(self.upd, text="", font=ctk.CTkFont(size=12, weight="bold"),
                                    text_color=BLUE)
        self.upd_lbl.pack(side="left", padx=(12, 8), pady=8)
        self.upd_btn = ctk.CTkButton(self.upd, text="Nu bijwerken", width=110, height=28, corner_radius=8,
                                     fg_color=BLUE, hover_color=("#1D4ED8", "#3B82F6"),
                                     font=ctk.CTkFont(size=12, weight="bold"), command=self.install_app_update)
        self.upd_btn.pack(side="left", pady=8)
        self.upd_later = ctk.CTkButton(self.upd, text="Later", width=56, height=28, corner_radius=8,
                                       fg_color="transparent", text_color=MUTED, hover_color=BORDER,
                                       font=ctk.CTkFont(size=12), command=self.upd.pack_forget)
        self.upd_later.pack(side="left", padx=(4, 8), pady=8)
        self.new_version = None

    def _build_input(self):
        card = ctk.CTkFrame(self, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        card.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 12))
        card.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        ctk.CTkLabel(top, text="Links", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkLabel(top, text="  één per regel", font=ctk.CTkFont(size=12), text_color=MUTED).pack(side="left")
        self._ghost(top, "Wissen", lambda: self.links.delete("1.0", "end"), 70).pack(side="right")
        self._ghost(top, "Plakken", self.paste, 70).pack(side="right", padx=6)

        self.links = ctk.CTkTextbox(card, height=72, corner_radius=10, border_width=1, border_color=BORDER,
                                    fg_color=("#F9FAFB", "#1A1B1E"),
                                    font=ctk.CTkFont(family="Consolas", size=12), wrap="none")
        self.links.grid(row=1, column=0, sticky="ew", padx=16)

        opts = ctk.CTkFrame(card, fg_color="transparent")
        opts.grid(row=2, column=0, sticky="ew", padx=16, pady=(12, 0))
        for c in (1, 3):
            opts.grid_columnconfigure(c, weight=1)

        s = self.settings
        self._lbl(opts, "Formaat").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.mode = ctk.CTkSegmentedButton(opts, values=["MP4", "MP3"], command=self.on_mode, **SEG)
        self.mode.set(s["mode"])
        self.mode.grid(row=0, column=1, sticky="w")

        self._lbl(opts, "Kwaliteit").grid(row=0, column=2, sticky="w", padx=(16, 10))
        self.quality = ctk.CTkOptionMenu(opts, values=[""], width=170, height=30, corner_radius=8,
                                         fg_color=("#E5E7EB", "#2A2B30"), button_color=("#E5E7EB", "#2A2B30"),
                                         button_hover_color=("#D1D5DB", "#34353B"), text_color=TEXT,
                                         command=lambda _: self.persist())
        self.quality.grid(row=0, column=3, sticky="w")

        self._lbl(opts, "Playlist").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(10, 0))
        self.playlist = ctk.CTkSegmentedButton(opts, values=["Alleen deze video", "Hele afspeellijst"],
                                               command=lambda _: self.persist(), **SEG)
        self.playlist.set(s["playlist"])
        self.playlist.grid(row=1, column=1, sticky="w", pady=(10, 0))

        self._lbl(opts, "Tegelijk").grid(row=1, column=2, sticky="w", padx=(16, 10), pady=(10, 0))
        self.parallel = ctk.CTkSegmentedButton(opts, values=["1", "2", "3", "4", "5"],
                                               command=lambda _: self.persist(), **SEG)
        self.parallel.set(str(s["parallel"]))
        self.parallel.grid(row=1, column=3, sticky="w", pady=(10, 0))

        self._lbl(opts, "Opslaan in").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=(10, 0))
        folder = ctk.CTkFrame(opts, fg_color="transparent")
        folder.grid(row=2, column=1, columnspan=3, sticky="ew", pady=(10, 0))
        folder.grid_columnconfigure(0, weight=1)
        self.outdir = ctk.StringVar(value=s["outdir"])
        ctk.CTkEntry(folder, textvariable=self.outdir, height=30, corner_radius=8,
                     border_width=1, border_color=BORDER).grid(row=0, column=0, sticky="ew")
        self._ghost(folder, "Wijzigen", self.browse, 80).grid(row=0, column=1, padx=(6, 0))

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.grid(row=3, column=0, sticky="ew", padx=16, pady=16)
        btns.grid_columnconfigure(0, weight=1)
        self.dl_btn = ctk.CTkButton(btns, text="Downloaden", height=42, corner_radius=10,
                                    font=ctk.CTkFont(size=14, weight="bold"),
                                    fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self.add_links)
        self.dl_btn.grid(row=0, column=0, sticky="ew")
        self.stop_all_btn = ctk.CTkButton(btns, text="■  Alles stoppen", width=170, height=42, corner_radius=10,
                                          font=ctk.CTkFont(size=14, weight="bold"), fg_color="transparent",
                                          border_width=2, border_color=RED, text_color=RED,
                                          text_color_disabled=("#D1D5DB", "#4B4C55"),
                                          hover_color=("#FEE2E2", "#3B1F22"), command=self.confirm_cancel_all)
        self.stop_all_btn.grid(row=0, column=1, padx=(10, 0))

        # Installatie-melding (eerste start)
        self.setup = ctk.CTkFrame(card, fg_color="transparent")
        self.setup_lbl = ctk.CTkLabel(self.setup, text="", font=ctk.CTkFont(size=12), text_color=MUTED)
        self.setup_lbl.pack(anchor="w")
        self.setup_bar = ctk.CTkProgressBar(self.setup, height=6, progress_color=ACCENT)
        self.setup_bar.pack(fill="x", pady=(4, 0))
        self.on_mode(s["mode"], init=True)

    def _build_list(self):
        card = ctk.CTkFrame(self, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        card.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 12))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        ctk.CTkLabel(head, text="Downloads", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        self.summary = ctk.CTkFrame(head, fg_color="transparent", width=1, height=1)
        self.summary.pack(side="left", padx=12)
        self.sum_labels = {}
        for key, color in (("gereed", GREEN), ("mislukt", RED), ("bezig", BLUE), ("wachten", MUTED)):
            lbl = ctk.CTkLabel(self.summary, text="", font=ctk.CTkFont(size=12, weight="bold"),
                               text_color=color)
            self.sum_labels[key] = lbl
        self._ghost(head, "Lijst leegmaken", self.clear_list, 120).pack(side="right")
        self.retry_btn = self._ghost(head, "Mislukte opnieuw", self.retry_failed, 125)
        self.retry_btn.pack(side="right", padx=6)

        self.list = ctk.CTkScrollableFrame(card, fg_color="transparent")
        self.list.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 10))
        self.list.grid_columnconfigure(0, weight=1)
        self.empty = ctk.CTkLabel(self.list, text="Nog geen downloads.\nPlak een link en klik op Downloaden.",
                                  text_color=MUTED, font=ctk.CTkFont(size=13), justify="center")
        self.empty.pack(pady=50)

    def _build_footer(self):
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 16))
        self._ghost(foot, "Map openen", self.open_folder, 100).pack(side="left")
        self.update_btn = self._ghost(foot, "Downloader bijwerken", self.update_ytdlp, 160)
        self.update_btn.pack(side="right")
        self.foot_lbl = ctk.CTkLabel(foot, text=f"v{APP_VERSION}", text_color=MUTED, font=ctk.CTkFont(size=11))
        self.foot_lbl.pack(side="right", padx=10)

    def _lbl(self, master, text):
        return ctk.CTkLabel(master, text=text, font=ctk.CTkFont(size=12), text_color=MUTED)

    def _ghost(self, master, text, cmd, width):
        return ctk.CTkButton(master, text=text, command=cmd, width=width, height=30, corner_radius=8,
                             fg_color="transparent", border_width=1, border_color=BORDER,
                             text_color=("#111827", "#E5E7EB"), hover_color=BORDER,
                             font=ctk.CTkFont(size=12))

    # ---- opties ---------------------------------------------------------- #
    def on_mode(self, mode, init=False):
        if mode == "MP4":
            self.quality.configure(values=list(VIDEO_QUALITIES))
            self.quality.set(self.settings.get("vq", "Beste kwaliteit"))
        else:
            self.quality.configure(values=list(AUDIO_QUALITIES))
            self.quality.set(self.settings.get("aq", "192 kbps"))
        if not init:
            self.persist()

    def persist(self):
        s = self.settings
        s["mode"] = self.mode.get()
        if s["mode"] == "MP4":
            s["vq"] = self.quality.get()
        else:
            s["aq"] = self.quality.get()
        s["playlist"] = self.playlist.get()
        s["parallel"] = int(self.parallel.get())
        s["outdir"] = self.outdir.get()
        save_settings(s)

    def paste(self):
        try:
            text = self.clipboard_get().strip()
        except tk.TclError:
            return
        cur = self.links.get("1.0", "end").strip()
        self.links.insert("end", ("\n" if cur else "") + text)

    def browse(self):
        path = filedialog.askdirectory(initialdir=self.outdir.get() or None, title="Kies een map")
        if path:
            self.outdir.set(os.path.normpath(path))
            self.persist()

    def open_folder(self):
        path = self.outdir.get()
        if os.path.isdir(path):
            self._open(path)

    def _open(self, path, select=False):
        if IS_WIN:
            if select:
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            else:
                os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path) if select else path])

    # ---- taken ----------------------------------------------------------- #
    def add_links(self):
        if not self.ready:
            messagebox.showinfo(APP_NAME, "Even geduld, de benodigde onderdelen worden nog gedownload.")
            return
        urls = [u.strip() for u in self.links.get("1.0", "end").splitlines() if u.strip()]
        if not urls:
            messagebox.showinfo(APP_NAME, "Plak eerst een of meer links.")
            return
        outdir = self.outdir.get().strip()
        try:
            os.makedirs(outdir, exist_ok=True)
        except OSError:
            messagebox.showerror(APP_NAME, "De gekozen map bestaat niet en kan niet worden aangemaakt.")
            return
        self.persist()
        expand = self.playlist.get() == "Hele afspeellijst"
        for url in urls:
            job = Job(url, self.mode.get(), self.quality.get(), outdir, expand=expand)
            self._add_job(job)
            if expand:
                threading.Thread(target=self.expand_worker, args=(job,), daemon=True).start()
        self.links.delete("1.0", "end")
        self.update_summary()

    def _add_job(self, job, after=None):
        if self.empty.winfo_manager():
            self.empty.pack_forget()
        job.row = JobRow(self.list, job, self)
        if after is not None:
            job.row.pack(fill="x", padx=4, pady=4, after=after.row)
            self.jobs.insert(self.jobs.index(after) + 1, job)
        else:
            job.row.pack(fill="x", padx=4, pady=4)
            self.jobs.append(job)

    def _remove_job(self, job):
        job.row.destroy()
        self.jobs.remove(job)
        if not self.jobs:
            self.empty.pack(pady=50)

    def cancel_job(self, job):
        job.cancelled = True
        if job.state == "bezig" or job.state == "ophalen":
            kill_tree(job.proc)
        if job.state in ("wachten", "ophalen"):
            job.state = "gestopt"
        job.row.refresh()
        self.update_summary()

    def retry_job(self, job):
        job.percent, job.detail, job.error, job.cancelled, job.retried = 0, "", "", False, False
        self.retry_at.pop(job.id, None)
        if job.expand:
            job.state = "ophalen"
            threading.Thread(target=self.expand_worker, args=(job,), daemon=True).start()
        else:
            job.state = "wachten"
        job.row.refresh()
        self.update_summary()

    def show_file(self, job):
        if job.filepath and os.path.exists(job.filepath):
            self._open(job.filepath, select=True)
        else:
            self._open(job.outdir)

    def cancel_all(self):
        for j in self.jobs:
            if j.state in ("bezig", "wachten", "ophalen"):
                self.cancel_job(j)

    def confirm_cancel_all(self):
        active = [j for j in self.jobs if j.state in ("bezig", "wachten", "ophalen")]
        if not active:
            return
        if messagebox.askyesno(APP_NAME, f"{len(active)} download(s) stoppen en annuleren?\n\n"
                                         "Wat al klaar is, blijft gewoon bewaard."):
            self.cancel_all()

    def remove_job(self, job):
        """Regel uit de lijst halen (bijv. verkeerde link); loopt hij nog, dan eerst stoppen."""
        if job.state in ("bezig", "wachten", "ophalen"):
            self.cancel_job(job)
        self.retry_at.pop(job.id, None)
        if job in self.jobs:
            self._remove_job(job)
        self.update_summary()

    def clear_list(self):
        active = [j for j in self.jobs if j.state in ("bezig", "wachten", "ophalen")]
        if active and not messagebox.askyesno(
                APP_NAME, f"Er lopen nog {len(active)} download(s). Die worden gestopt. Lijst toch leegmaken?"):
            return
        for j in list(self.jobs):
            self.remove_job(j)

    def retry_failed(self):
        for j in self.jobs:
            if j.state in ("mislukt", "gestopt"):
                self.retry_job(j)

    def clear_done(self):
        for j in [j for j in self.jobs if j.state == "gereed"]:
            self._remove_job(j)
        self.update_summary()

    def update_summary(self):
        counts = {k: 0 for k in self.sum_labels}
        for j in self.jobs:
            k = "wachten" if j.state == "ophalen" else j.state
            if k in counts:
                counts[k] += 1
        names = {"gereed": "gereed", "mislukt": "mislukt", "bezig": "bezig", "wachten": "in wachtrij"}
        busy = counts["bezig"] + counts["wachten"]
        self.stop_all_btn.configure(state="normal" if busy else "disabled",
                                    border_color=RED if busy else BORDER)
        for k, lbl in self.sum_labels.items():
            if counts[k]:
                lbl.configure(text=f"● {counts[k]} {names[k]}")
                lbl.pack(side="left", padx=(0, 10))
            else:
                lbl.pack_forget()

    # ---- workers --------------------------------------------------------- #
    def expand_worker(self, job):
        """Haal de video's uit een playlist op; elke video wordt een eigen regel."""
        entries, last_err = [], ""
        try:
            job.proc = popen(build_playlist_command(job.url))
            for line in job.proc.stdout:
                line = line.rstrip()
                if "\t" in line and not line.startswith(("ERROR", "WARNING")):
                    url, title = line.split("\t", 1)
                    if url and url != "NA":
                        entries.append((url, None if title == "NA" else title))
                elif line.startswith("ERROR:"):
                    last_err = line[6:].strip()
            job.proc.wait()
        except OSError as e:
            last_err = str(e)
        self.events.put(("expanded", job, entries, last_err))

    def download_worker(self, job):
        last_err = ""
        try:
            job.proc = popen(build_download_command(job))
            for raw in job.proc.stdout:
                line = raw.rstrip()
                if not line:
                    continue
                m = PROGRESS_RE.match(line)
                if m:
                    pct = float(m.group(1))
                    parts = [f"{pct:.0f}%"]
                    speed, eta = m.group(2).strip(), m.group(3).strip()
                    if speed and "Unknown" not in speed and speed != "NA":
                        parts.append(speed)
                    if eta and "Unknown" not in eta and eta != "NA":
                        parts.append(f"nog {eta}")
                    self.events.put(("progress", job, pct, "  ·  ".join(parts)))
                elif line.startswith("TITLE "):
                    self.events.put(("title", job, line[6:]))
                elif line.startswith("FILE "):
                    job.filepath = line[5:]
                elif line.startswith("ERROR:"):
                    last_err = line[6:].strip()
            code = job.proc.wait()
            if code == 0 and job.filepath and AUDIO_TAG in os.path.basename(job.filepath):
                final = os.path.join(os.path.dirname(job.filepath),
                                     os.path.basename(job.filepath).replace(AUDIO_TAG, "", 1))
                os.replace(job.filepath, final)
                job.filepath = final
        except OSError as e:
            code, last_err = 1, str(e)
        self.events.put(("finished", job, code, last_err))

    def start_job(self, job):
        job.state, job.percent, job.detail = "bezig", 0, ""
        job.row.refresh()
        threading.Thread(target=self.download_worker, args=(job,), daemon=True).start()

    # ---- hoofdlus -------------------------------------------------------- #
    def tick(self):
        changed = set()
        summary = False
        try:
            while True:
                ev = self.events.get_nowait()
                kind, job = ev[0], ev[1]
                if kind == "progress":
                    _, _, pct, text = ev
                    job.percent, job.detail = pct, text
                    if pct >= 100:
                        job.detail = "Verwerken…" if job.mode == "MP4" else "Omzetten naar MP3…"
                    changed.add(job)
                elif kind == "title":
                    job.title = ev[2]
                    changed.add(job)
                elif kind == "finished":
                    _, _, code, err = ev
                    if job.cancelled:
                        job.state = "gestopt"
                    elif code == 0:
                        job.state, job.percent = "gereed", 100
                    elif "403" in err and not job.retried:
                        # YouTube weigert soms tijdelijk; automatisch één keer opnieuw proberen
                        job.retried = True
                        job.state, job.percent = "wachten", 0
                        job.detail = "Toegang geweigerd, over enkele seconden opnieuw proberen…"
                        self.retry_at[job.id] = self._now() + 4
                    else:
                        job.state, job.error = "mislukt", friendly_error(err)
                    job.proc = None
                    changed.add(job)
                    summary = True
                elif kind == "expanded":
                    self._handle_expanded(job, ev[2], ev[3])
                    summary = True
                elif kind == "setup":
                    _, _, frac, text = ev
                    self.setup_lbl.configure(text=text)
                    if frac is None:
                        self.setup_bar.configure(mode="indeterminate")
                        self.setup_bar.start()
                    else:
                        self.setup_bar.configure(mode="determinate")
                        self.setup_bar.set(frac)
                elif kind == "setup_done":
                    self._setup_done(ev[2])
                elif kind == "app_update":
                    self._show_app_update(ev[2])
                elif kind == "app_update_progress":
                    self.upd_lbl.configure(text=ev[2])
                elif kind == "app_update_ready":
                    self._run_app_update(ev[2], ev[3])
                elif kind == "updated":
                    self._update_done(ev[2], ev[3])
        except queue.Empty:
            pass

        # wachtrij: start nieuwe downloads tot het ingestelde aantal tegelijk
        if self.ready and not self.updating:
            limit = int(self.parallel.get())
            running = sum(1 for j in self.jobs if j.state == "bezig")
            for j in self.jobs:
                if running >= limit:
                    break
                if j.state == "wachten" and self.retry_at.get(j.id, 0) <= self._now():
                    self.retry_at.pop(j.id, None)
                    self.start_job(j)
                    running += 1
                    summary = True

        for j in changed:
            if j.row is not None and j.row.winfo_exists():
                j.row.refresh()
        if summary:
            self.update_summary()
        self.after(150, self.tick)

    @staticmethod
    def _now():
        return time.monotonic()

    def _handle_expanded(self, job, entries, err):
        if not job.row or not job.row.winfo_exists():
            return
        if job.cancelled:
            job.state = "gestopt"
            job.row.refresh()
            return
        if not entries:
            job.state, job.error = "mislukt", friendly_error(err) if err else "Geen video's gevonden"
            job.row.refresh()
            return
        job.expand = False
        if len(entries) == 1:
            job.url, job.title = entries[0][0], entries[0][1] or job.title
            job.state = "wachten"
            job.row.refresh()
            return
        prev = job
        for url, title in entries:
            new = Job(url, job.mode, job.quality, job.outdir, title=title)
            self._add_job(new, after=prev)
            prev = new
        self._remove_job(job)

    # ---- eerste start / bijwerken --------------------------------------- #
    def install(self):
        self.dl_btn.configure(state="disabled", text="Bezig met voorbereiden…")
        self.setup.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 14))
        self.events.put(("setup", None, None, "Eerste start: benodigde onderdelen downloaden (eenmalig)…"))

        def work():
            try:
                install_tools(lambda f, t: self.events.put(("setup", None, f, t)))
                self.events.put(("setup_done", None, None))
            except Exception as e:  # noqa: BLE001
                self.events.put(("setup_done", None, str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _setup_done(self, err):
        self.setup_bar.stop()
        if err:
            self.setup_lbl.configure(text="Downloaden van onderdelen mislukt. Controleer je internet en "
                                          "start het programma opnieuw.", text_color=RED)
            self.dl_btn.configure(text="Niet beschikbaar")
            return
        self.setup.grid_forget()
        self.ready = True
        self.dl_btn.configure(state="normal", text="Downloaden")

    def update_ytdlp(self, silent=False):
        if not self.ready or self.updating:
            return
        if any(j.state == "bezig" for j in self.jobs):
            if not silent:
                messagebox.showinfo(APP_NAME, "Wacht tot de lopende downloads klaar zijn.")
            return
        self.updating = True
        self.update_silent = silent
        self.update_btn.configure(state="disabled", text="Bijwerken…")
        self.foot_lbl.configure(text="Downloader controleren op updates…")

        def work():
            out, code = "", 1
            try:
                p = popen([YTDLP_EXE, "--update-to", "nightly"])
                out = p.communicate()[0]
                code = p.returncode
            except OSError as e:
                out = str(e)
            self.events.put(("updated", None, code, out))

        threading.Thread(target=work, daemon=True).start()

    def _update_done(self, code, out):
        self.updating = False
        self.update_btn.configure(state="normal", text="Downloader bijwerken")
        if code == 0:
            msg = "Downloader is up-to-date." if "up to date" in out.lower() else "Downloader is bijgewerkt."
            self.foot_lbl.configure(text=msg)
        elif self.update_silent:
            self.foot_lbl.configure(text="Controleren op updates mislukt")
        else:
            self.foot_lbl.configure(text=f"v{APP_VERSION}")
            messagebox.showwarning(APP_NAME, "Bijwerken mislukt:\n\n" + out.strip()[-500:])

    # ---- updates van het programma zelf ---------------------------------- #
    def start_app_update_check(self):
        def work():
            try:
                found = check_app_update()
            except Exception:  # noqa: BLE001  (geen internet e.d.: stil negeren)
                found = None
            if found:
                self.events.put(("app_update", None, found))

        threading.Thread(target=work, daemon=True).start()

    def _show_app_update(self, found):
        self.new_version = found
        self.upd_lbl.configure(text=f"Nieuwe versie {found[0]} beschikbaar")
        self.upd.pack(side="right")

    def install_app_update(self):
        if not self.new_version:
            return
        active = [j for j in self.jobs if j.state in ("bezig", "wachten", "ophalen")]
        if active and not messagebox.askyesno(
                APP_NAME, f"Er lopen nog {len(active)} download(s). Die worden gestopt.\n\nNu bijwerken?"):
            return
        self.upd_btn.configure(state="disabled", text="Bezig…")
        self.upd_later.pack_forget()
        version, url = self.new_version

        def work():
            dest = os.path.join(BASE_DIR, f"Setup-{version}.exe")
            try:
                os.makedirs(BASE_DIR, exist_ok=True)
                download_file(url, dest, lambda p, t: self.events.put(
                    ("app_update_progress", None, f"Update downloaden… {t}")))
                self.events.put(("app_update_ready", None, dest, None))
            except Exception as e:  # noqa: BLE001
                self.events.put(("app_update_ready", None, None, str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _run_app_update(self, setup, err):
        if err or not setup:
            self.upd_lbl.configure(text="Update downloaden mislukt")
            self.upd_btn.configure(state="normal", text="Opnieuw")
            return
        self.upd_lbl.configure(text="Installeren… het programma start zo opnieuw")
        for j in self.jobs:
            if j.state in ("bezig", "ophalen"):
                j.cancelled = True
                kill_tree(j.proc)
        self.persist()
        # stille installatie; de installer start het programma daarna zelf opnieuw
        subprocess.Popen([setup, "/S"], close_fds=True,
                         creationflags=0x00000008 if IS_WIN else 0)  # DETACHED_PROCESS
        self.after(300, self.destroy)

    def on_close(self):
        busy = any(j.state in ("bezig", "wachten", "ophalen") for j in self.jobs)
        if busy and not messagebox.askyesno(APP_NAME, "Er lopen nog downloads. Toch afsluiten?"):
            return
        for j in self.jobs:
            if j.state in ("bezig", "ophalen"):
                j.cancelled = True
                kill_tree(j.proc)
        self.persist()
        self.destroy()


def main():
    if IS_WIN:
        try:  # eigen icoon in de taakbalk i.p.v. het Python-icoon
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("VideoAudioConverter.App")
        except Exception:  # noqa: BLE001
            pass
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    App().mainloop()


if __name__ == "__main__":
    main()
