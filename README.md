# Video/Audio Converter

Windows-programma om video's (MP4) en audio (MP3) te downloaden van YouTube en 1000+ andere sites
(Vimeo, TikTok, Instagram, Facebook, X, SoundCloud, ...).

- Meerdere downloads tegelijk (1 t/m 5)
- Alleen één video of een hele afspeellijst
- Overzicht per download: gereed, mislukt (met reden), bezig, in de wachtrij
- Licht en donker thema (volgt Windows)
- Werkt zichzelf bij: de downloader (yt-dlp nightly) bij elke start, en het programma via GitHub Releases

## Installeren

Download `Video-Audio-Converter-Setup.exe` bij de nieuwste [Release](../../releases/latest) en voer hem uit.
Windows SmartScreen kan waarschuwen omdat de installer niet ondertekend is:
klik op **Meer informatie** en dan op **Toch uitvoeren**.

## Een nieuwe versie uitbrengen

1. Pas de code aan in `src/` en zet de wijziging op GitHub (commit + push naar `main`).
2. Ga naar **Releases → Draft a new release**.
3. Typ bij **Choose a tag** een nieuw versienummer, bijv. `v2.4.0`, en kies *Create new tag*.
   Vul eventueel een titel en beschrijving in en klik **Publish release**.
4. GitHub Actions bouwt automatisch de installer en zet `Video-Audio-Converter-Setup.exe`
   bij die release (zie het tabblad **Actions**, duurt ± 2 minuten).
5. Geïnstalleerde programma's zien de nieuwe versie bij de volgende start en tonen
   *"Nieuwe versie beschikbaar – Nu bijwerken"*. Eén klik installeert hem en start het programma opnieuw.

Het versienummer komt uit de tag; je hoeft het nergens anders aan te passen.

## Hoe het werkt

| Onderdeel | Waarvoor | Waar vandaan |
|---|---|---|
| `src/video_audio_converter.py` | Het programma (Python + customtkinter) | deze repository |
| Ingebouwde Python 3.12 | Draait het programma, zit in de installer | python-build-standalone |
| yt-dlp | Het eigenlijke downloaden | eerste start, daarna elke start bijgewerkt (nightly) |
| FFmpeg | Samenvoegen beeld + geluid, omzetten naar MP3 | eerste start (eenmalig) |
| Deno | Nodig voor YouTube | eerste start (eenmalig) |

De onderdelen worden opgeslagen in `%LOCALAPPDATA%\VideoAudioConverter`.
De installer wordt gebouwd op Linux met NSIS: `scripts/build_installer.sh <versie>`.

## Let op

Download alleen materiaal waarvoor je toestemming hebt of dat vrij te gebruiken is.

## Licentie

MIT – zie [LICENSE](LICENSE). © 2026 Bas Verbeek
