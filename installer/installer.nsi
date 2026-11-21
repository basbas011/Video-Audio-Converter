; Video/Audio Converter - Windows installer (NSIS 3)
Unicode true
SetCompressor /SOLID lzma

!define APPNAME "Video-Audio Converter"
!define DISPLAYNAME "Video/Audio Converter"
!ifndef VERSION
  !define VERSION "0.0.0"
!endif
!ifndef OUTFILE
  !define OUTFILE "Video-Audio-Converter-Setup.exe"
!endif
!define REGKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\VideoAudioConverter"
!ifndef STAGE
  !define STAGE "stage"
!endif

Name "${DISPLAYNAME}"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\${APPNAME}"
InstallDirRegKey HKCU "${REGKEY}" "InstallLocation"
RequestExecutionLevel user
BrandingText "${DISPLAYNAME} ${VERSION}"

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${DISPLAYNAME}"
VIAddVersionKey "FileDescription" "${DISPLAYNAME} installatie"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "${DISPLAYNAME}"

!include "MUI2.nsh"
!define MUI_ICON "${STAGE}\app\icon.ico"
!define MUI_UNICON "${STAGE}\app\icon.ico"
!define MUI_ABORTWARNING
!define MUI_COMPONENTSPAGE_NODESC

!define MUI_WELCOMEPAGE_TEXT "Met ${DISPLAYNAME} download je video's (MP4) en muziek (MP3) van YouTube en meer dan 1000 andere websites.$\r$\n$\r$\nKlik op Volgende om verder te gaan."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "${DISPLAYNAME} nu starten"
!define MUI_FINISHPAGE_RUN_FUNCTION StartApp
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Dutch"

Function .onInit
  ; bij een automatische update (stil, /S) even wachten tot het programma is afgesloten
  IfSilent 0 +2
    Sleep 2500
FunctionEnd

Function .onInstSuccess
  ; na een stille update het programma weer starten
  IfSilent 0 +2
    Exec '"$INSTDIR\python\pythonw.exe" "$INSTDIR\app\video_audio_converter.py"'
FunctionEnd

Function StartApp
  ExecShell "" "$INSTDIR\python\pythonw.exe" '"$INSTDIR\app\video_audio_converter.py"'
FunctionEnd

Section "Programma (vereist)" SecMain
  SectionIn RO
  ; oude versie eerst opruimen
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\app"
  SetOutPath "$INSTDIR"
  File /r "${STAGE}\python"
  File /r "${STAGE}\app"
  WriteUninstaller "$INSTDIR\Verwijderen.exe"

  WriteRegStr HKCU "${REGKEY}" "DisplayName" "${DISPLAYNAME}"
  WriteRegStr HKCU "${REGKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${REGKEY}" "DisplayIcon" "$INSTDIR\app\icon.ico"
  WriteRegStr HKCU "${REGKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${REGKEY}" "UninstallString" '"$INSTDIR\Verwijderen.exe"'
  WriteRegStr HKCU "${REGKEY}" "Publisher" "${DISPLAYNAME}"
  WriteRegDWORD HKCU "${REGKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${REGKEY}" "NoRepair" 1
SectionEnd

Section "Snelkoppeling op het bureaublad" SecDesktop
  ; bij een stille update alleen vernieuwen als de snelkoppeling al bestond
  IfSilent 0 +3
    IfFileExists "$DESKTOP\${DISPLAYNAME}.lnk" +2 0
      Return
  CreateShortCut "$DESKTOP\${DISPLAYNAME}.lnk" "$INSTDIR\python\pythonw.exe" '"$INSTDIR\app\video_audio_converter.py"' "$INSTDIR\app\icon.ico" 0 SW_SHOWNORMAL "" "${DISPLAYNAME}"
SectionEnd

Section "Snelkoppeling in het Startmenu" SecStart
  IfSilent 0 +3
    IfFileExists "$SMPROGRAMS\${DISPLAYNAME}.lnk" +2 0
      Return
  CreateShortCut "$SMPROGRAMS\${DISPLAYNAME}.lnk" "$INSTDIR\python\pythonw.exe" '"$INSTDIR\app\video_audio_converter.py"' "$INSTDIR\app\icon.ico" 0 SW_SHOWNORMAL "" "${DISPLAYNAME}"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\${DISPLAYNAME}.lnk"
  Delete "$SMPROGRAMS\${DISPLAYNAME}.lnk"
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\app"
  Delete "$INSTDIR\Verwijderen.exe"
  RMDir "$INSTDIR"
  ; gedownloade onderdelen (yt-dlp, ffmpeg, deno) en instellingen
  RMDir /r "$LOCALAPPDATA\VideoAudioConverter"
  DeleteRegKey HKCU "${REGKEY}"
SectionEnd
