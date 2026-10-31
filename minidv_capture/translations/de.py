"""German interface translation."""

CODE = 'de'
NAME = 'Deutsch'
FLAG = '🇩🇪'
STRINGS = {
    'Capture settings': 'Aufnahme-Einstellungen',
    'Conversion': 'Konvertierung',
    'Record': 'Aufnahme',
    'Back': 'Zurück',
    'Next': 'Weiter',
    'Show jobs and log': 'Aufträge und Protokoll anzeigen',
    'Setup': 'Einrichtung', '1 · Camera': '1 · Kamera', '2 · Capture': '2 · Aufnahme',
    '3 · Background conversion': '3 · Konvertierung im Hintergrund',
    '↻  Rescan cameras': '↻  Kameras neu suchen', 'Browse …': 'Durchsuchen …',
    'Output folder': 'Zielordner', 'Tape name': 'Kassettenname', 'Transport': 'Steuerung',
    'Manual · PLAY on camera': 'Manuell · PLAY an der Kamera',
    'Automatic · AV/C': 'Automatisch · AV/C',
    'Rewind automatically before capture': 'Vor der Aufnahme automatisch zurückspulen',
    'Optional time limit': 'Optionale Zeitbegrenzung', 'No time limit': 'Keine Zeitbegrenzung',
    'Select PLAYER/VCR mode. Start capture here, then press PLAY on the camera.':
        'PLAYER/VCR-Modus wählen. Aufnahme hier starten und dann PLAY an der Kamera drücken.',
    'Start next capture automatically after changing the tape': 'Nach Kassettenwechsel automatisch weiter aufnehmen',
    'Format': 'Format', 'Quality': 'Qualität',
    'Deinterlace · smooth 50p/59.94p': 'Deinterlacing · flüssige 50p/59,94p',
    'Delete original DV after successful verification': 'Original-DV nach erfolgreicher Prüfung löschen',
    'Pause queue': 'Warteschlange pausieren', 'Resume queue': 'Warteschlange fortsetzen',
    'Retry selected conversion': 'Ausgewählte Konvertierung wiederholen', 'Open folder': 'Ordner öffnen',
    'Clear history': 'Verlauf leeren', 'Start capture': 'Aufnahme starten',
    'Stop && convert': 'Stoppen && konvertieren', 'Cancel capture': 'Aufnahme abbrechen',
    'Ready': 'Bereit', 'Tape': 'Kassette', 'Camera': 'Kamera', 'Status': 'Status',
    'Progress': 'Fortschritt', 'Details': 'Details', 'Live preview': 'Live-Vorschau',
    'Check devices': 'Geräte prüfen', 'Retry capture': 'Aufnahme erneut versuchen',
    'All components ready': 'Alle Komponenten bereit', 'Waiting for PLAY': 'Warte auf PLAY',
    'Starting dvgrab…': 'dvgrab wird gestartet …',
    'Missing components: ': 'Fehlende Komponenten: ',
    ' · Install missing components in Setup.': ' · Fehlende Komponenten über Einrichtung installieren.',
    'Device access ready': 'Gerätezugriff bereit',
    'Access denied – open Setup': 'Zugriff verweigert – Einrichtung öffnen',
    'No camera connected. Select PLAYER/VCR mode and connect via FireWire.':
        'Keine Kamera verbunden. PLAYER/VCR-Modus wählen und per FireWire verbinden.',
    'DV data is arriving and the recording file is growing.':
        'DV-Daten treffen ein und die Aufnahmedatei wächst.',
    'dvgrab is running. No DV data has arrived yet. In Manual mode, press PLAY on the camera; otherwise check camera mode and connection.':
        'dvgrab läuft, aber es treffen noch keine DV-Daten ein. Im manuellen Modus PLAY an der Kamera drücken, sonst Kameramodus und Verbindung prüfen.',
    'Starting capture process': 'Aufnahmeprozess wird gestartet',
    'Select PLAYER/VCR mode on the camera. The app starts playback automatically.':
        'PLAYER/VCR-Modus an der Kamera wählen. Die App startet die Wiedergabe automatisch.',
    'Capturing': 'Aufnahme läuft', 'Queued': 'Wartet auf Konvertierung',
    'Converting': 'Konvertierung läuft', 'Verifying output': 'Ausgabe wird geprüft',
    'Done': 'Fertig', 'Capture error': 'Aufnahmefehler', 'Cancelled': 'Abgebrochen',
    'Interrupted': 'Unterbrochen', 'Conversion error': 'Konvertierungsfehler',
    'Capture ≈': 'Aufnahme ≈', 'Conversion': 'Konvertierung', 'Stopped': 'Gestoppt',
    'Waiting for conversion': 'Wartet auf Konvertierung', 'Converting video': 'Video wird konvertiert',
    'Verifying video and audio': 'Video und Ton werden geprüft',
    'Complete · output verified': 'Abgeschlossen · Ausgabe geprüft',
    'Cancelled · raw footage kept': 'Abgebrochen · Rohmaterial behalten',
    'Interrupted · raw footage kept': 'Unterbrochen · Rohmaterial behalten',
    'Waiting for DV data / rewinding': 'Wartet auf DV-Daten / Spulen',
    'No DV data arrived. Check camera power, PLAYER/VCR mode and FireWire cable. Run a device check, then retry the capture.':
        'Keine DV-Daten eingetroffen. Stromversorgung, PLAYER/VCR-Modus und FireWire-Kabel prüfen. Geräte prüfen und Aufnahme erneut versuchen.',
    'Capture stopped': 'Aufnahme angehalten',
    'Automatically increment tape name for the next tape': 'Kassettennamen für die nächste Kassette automatisch erhöhen',
    'When enabled, Tape8-001 is followed by Tape9-001. When disabled, captures keep the same tape name and folder numbering continues, for example Tape8-002.':
        'Aktiviert folgt auf Tape8-001 der Name Tape9-001. Deaktiviert bleibt der Kassettenname gleich und die Ordnernummer läuft weiter, zum Beispiel Tape8-002.',
    'Raw footage is kept by default. AVI/DV remuxes without quality loss.\nYou can capture the next tape while conversion runs.':
        'Rohmaterial bleibt standardmäßig erhalten. AVI/DV wird ohne Qualitätsverlust umverpackt.\nWährend der Konvertierung kann die nächste Kassette aufgenommen werden.',
    'Capture request accepted. Waiting for dvgrab to start…': 'Aufnahmeanfrage angenommen. Warte auf den Start von dvgrab …',
    'Camera not found. Check power, PLAYER/VCR mode and FireWire cable, then check devices and retry.':
        'Kamera nicht gefunden. Stromversorgung, PLAYER/VCR-Modus und FireWire-Kabel prüfen, danach Geräte prüfen und erneut versuchen.',
    'dvgrab started; waiting for PLAY': 'dvgrab gestartet; warte auf PLAY',
    'Waiting for DV data (may be rewinding)': 'Warte auf DV-Daten (eventuell wird zurückgespult)',
    'Waiting for DV data': 'Warte auf DV-Daten',
    'DV data arriving; capturing': 'DV-Daten treffen ein; Aufnahme läuft',
    'Capturing · DV data arriving': 'Aufnahme läuft · DV-Daten treffen ein',
    'Stopping capture…': 'Aufnahme wird beendet …',
    'Capture estimate based on 90 minutes. This does not detect the end of the tape.':
        'Aufnahmeschätzung auf Basis von 90 Minuten. Das Kassettenende wird nicht erkannt.',
    'Conversion includes output verification.': 'Die Konvertierung umfasst eine Prüfung der Ausgabe.',
    'Waiting for conversion': 'Wartet auf Konvertierung',
    'Rescan FireWire devices and access permissions, including after a disconnect.':
        'FireWire-Geräte und Zugriffsrechte erneut suchen, auch nach einer Verbindungsunterbrechung.',
    'Uses AV/C cassette detection and automatic playback. Falls back to Start next tape if unsupported.':
        'Nutzt die AV/C-Kassettenerkennung und automatische Wiedergabe. Falls nicht unterstützt, kann „Nächste Kassette starten“ verwendet werden.',
    'Only after duration, audio, video and full decoding checks. Originals are kept if any check fails.':
        'Nur nach Prüfung von Dauer, Ton, Bild und vollständiger Dekodierung. Bei einem Fehler bleibt das Original erhalten.',
    'Finish capture, convert the footage and offer to start the next tape.':
        'Aufnahme beenden, Material konvertieren und anbieten, die nächste Kassette zu starten.',
    'Stop capture and keep the raw file without converting it.':
        'Aufnahme beenden und Rohdatei ohne Konvertierung behalten.',
    'Remove finished and failed jobs from the list. Keep video files and active or queued jobs.':
        'Abgeschlossene und fehlgeschlagene Aufträge aus der Liste entfernen. Videodateien sowie aktive und wartende Aufträge bleiben erhalten.',
    'Remove this entry from history. Keep all video and log files.':
        'Diesen Eintrag aus dem Verlauf entfernen. Video- und Protokolldateien bleiben erhalten.',
    'MiniDV Capture application version': 'Version der MiniDV-Capture-Anwendung',
    'Open': 'Öffnen', 'Quit': 'Beenden', 'Conversion complete': 'Konvertierung abgeschlossen',
    'No FireWire camera found. Check PLAYER/VCR mode, power and cable.':
        'Keine FireWire-Kamera gefunden. PLAYER/VCR-Modus, Stromversorgung und Kabel prüfen.',
    'No camera found on the FireWire bus. Check PLAYER/VCR mode and connection; if needed, power-cycle the camera and scan again.':
        'Keine Kamera am FireWire-Bus gefunden. PLAYER/VCR-Modus und Verbindung prüfen; falls nötig Kamera aus- und wieder einschalten und erneut suchen.',
    'Open Setup to enable FireWire access.': 'Über „Einrichtung“ den FireWire-Zugriff aktivieren.',
    'camera(s) found; ': 'Kamera(s) gefunden; ', ' accessible.': ' zugänglich.',
    'Scan at ': 'Suche um ',
    'Automatic start is off. Use Start next tape to continue.':
        'Automatischer Start ist aus. Zum Fortfahren „Nächste Kassette starten“ wählen.',
    'Inspecting source video': 'Quellvideo wird untersucht',
    'Checking output metadata': 'Ausgabedaten werden geprüft',
    'Retry conversion': 'Konvertierung erneut versuchen', 'Resume capture': 'Aufnahme fortsetzen',
    'Remove': 'Entfernen', 'Start next tape': 'Nächste Kassette starten', 'Close': 'Schließen',
    'Cancel': 'Abbrechen', 'Tape complete': 'Kassette fertig',
    'Conversion continues independently in the background.': 'Die Konvertierung läuft unabhängig im Hintergrund weiter.',
    'This closes the tape series. Conversions continue in the background.':
        'Damit wird diese Kassettenserie beendet. Konvertierungen laufen im Hintergrund weiter.',
    'Camera disconnected.': 'Kamera getrennt.',
    'The current conversion will finish; queued jobs will wait.':
        'Die laufende Konvertierung wird beendet; wartende Aufträge bleiben in der Warteschlange.',
    'Removed from history. Video and log files were kept.': 'Aus dem Verlauf entfernt. Video- und Protokolldateien bleiben erhalten.',
    'Cleared ': 'Verlauf geleert: ', ' history entries. Video files and pending jobs were kept.':
        ' Einträge entfernt. Videodateien und wartende Aufträge bleiben erhalten.',
    'Wait for active captures and conversions to finish before running setup.':
        'Warte mit der Einrichtung, bis laufende Aufnahmen und Konvertierungen beendet sind.',
    'Tasks running': 'Aufträge laufen',
    'Cancel active tasks and quit? Partial files will be kept; queued jobs will resume next time.':
        'Laufende Aufträge abbrechen und beenden? Teilaufnahmen bleiben erhalten; wartende Aufträge werden beim nächsten Start fortgesetzt.',
    'Preview starts with capture': 'Vorschau startet mit der Aufnahme',
    'No active capture selected': 'Keine aktive Aufnahme ausgewählt',
    'Live preview · muted · up to 5 fps': 'Live-Vorschau · ohne Ton · bis zu 5 Bilder/s',
    'Waiting for DV video …': 'Warte auf DV-Video …',
    'Preview unavailable. Capture continues independently.': 'Vorschau nicht verfügbar. Die Aufnahme läuft weiter.',
    'No new DV video · showing last frame': 'Kein neues DV-Video · letztes Bild wird angezeigt',
    'Waiting for readable DV data …': 'Warte auf lesbare DV-Daten …',
    'Install && set up': 'Installieren && einrichten',
    'Install missing components and enable FireWire access. Administrator authorization is required.':
        'Fehlende Komponenten installieren und FireWire-Zugriff aktivieren. Dafür ist eine Administratorfreigabe erforderlich.',
    'Installing…': 'Installation läuft …',
    'Setup complete. Rescan the camera.': 'Einrichtung abgeschlossen. Kamera erneut suchen.',
    'Setup did not complete. Check the details above and retry.':
        'Einrichtung nicht abgeschlossen. Details oben prüfen und erneut versuchen.',
    'Could not start administrator authorization: ': 'Administratorfreigabe konnte nicht gestartet werden: ',
    'MiniDV Capture · Setup': 'MiniDV Capture · Einrichtung',
    'ready': 'bereit', 'missing': 'fehlt',
    'Setup supports Ubuntu/Debian (APT), Arch/CachyOS (pacman), and Fedora (DNF). You will be asked for administrator authorization. A udev rule enables FireWire access for the active local desktop session. The application itself runs without administrator privileges.':
        'Die Einrichtung unterstützt Ubuntu/Debian (APT), Arch/CachyOS (pacman) und Fedora (DNF). Du wirst um eine Administratorfreigabe gebeten. Eine udev-Regel aktiviert den FireWire-Zugriff für die aktive lokale Sitzung. Die Anwendung selbst läuft ohne Administratorrechte.',
    'Automatic tape detection is unavailable. Use Start next tape after changing the cassette.':
        'Automatische Kassettenerkennung ist nicht verfügbar. Nach dem Wechsel „Nächste Kassette starten“ wählen.',
    'Cassette removed. Insert the next tape; capture will start automatically.':
        'Kassette ausgeworfen. Nächste Kassette einlegen; die Aufnahme startet automatisch.',
    'Automatic mode: remove this cassette, then insert the next tape.':
        'Automatikmodus: Kassette auswerfen und anschließend die nächste einlegen.',
    'Waiting for a reliable cassette status. You can also use Start next tape.':
        'Warte auf eine zuverlässige Kassettenmeldung. Du kannst auch „Nächste Kassette starten“ wählen.',
    'Put the camera at the point where the capture stopped. The app cannot seek to the exact stop position. Capture will start without rewinding; press PLAY on the camera when the app is waiting. The new DV segment will be appended to the existing tape capture when you stop it.':
        'Spule die Kamera an die Stelle, an der die Aufnahme endete. Die App kann nicht exakt zu dieser Stelle suchen. Die Aufnahme startet ohne Zurückspulen; drücke PLAY an der Kamera, sobald die App wartet. Beim Beenden wird der neue DV-Abschnitt an die vorhandene Aufnahme angehängt.',
    ' – insert the next tape': ' – nächste Kassette einlegen',
    'Tape complete – insert the next tape.': 'Kassette fertig – nächste Kassette einlegen.',
    'No DV data received. Check PLAYER/VCR mode and PLAY.': 'Keine DV-Daten empfangen. PLAYER/VCR-Modus und PLAY prüfen.',
    'Signal lost: no new DV data for 30 seconds. Check manually whether the tape has ended.':
        'Signal verloren: Seit 30 Sekunden treffen keine DV-Daten ein. Prüfe, ob das Band zu Ende ist.',
    'No DV data for 60 seconds; treating this as tape end and starting conversion.':
        'Seit 60 Sekunden keine DV-Daten; das Bandende wird angenommen und die Konvertierung gestartet.',
    'Camera disconnected. Partial capture is kept.': 'Kamera getrennt. Die Teilaufnahme bleibt erhalten.',
    'Less than 512 MiB free. Capture stopped to protect your data.':
        'Weniger als 512 MiB frei. Die Aufnahme wurde zum Schutz deiner Daten beendet.',
    'Could not start dvgrab: ': 'dvgrab konnte nicht gestartet werden: ',
    'Capture was interrupted. Raw files are kept; resume capture or retry conversion.':
        'Aufnahme wurde unterbrochen. Rohdateien bleiben erhalten; Aufnahme fortsetzen oder Konvertierung wiederholen.',
    'Interrupted captures found. Raw files were kept.': 'Unterbrochene Aufnahmen gefunden. Rohdateien wurden behalten.',
    'Capture error': 'Aufnahmefehler', 'Cancelled; raw footage kept.': 'Abgebrochen; Rohmaterial wurde behalten.',
    'Incomplete capture or damaged/dropped frames. Check the raw footage and capture.log.':
        'Aufnahme unvollständig oder beschädigte/fehlende Bilder. Rohmaterial und capture.log prüfen.',
    'Capture estimate based on 90 minutes. This does not detect the end of the tape.':
        'Aufnahmeschätzung auf Basis von 90 Minuten. Das Kassettenende wird nicht erkannt.',
    'Capture ≈': 'Aufnahme ≈', 'Conversion': 'Konvertierung',
    'Waiting for DV data': 'Warte auf DV-Daten', 'No new DV data': 'Keine neuen DV-Daten',
    'No FireWire camera found. Check PLAYER/VCR mode, power and cable.':
        'Keine FireWire-Kamera gefunden. PLAYER/VCR-Modus, Stromversorgung und Kabel prüfen.',
    'A capture is already running on this FireWire bus. Parallel capture requires separate controllers.':
        'An diesem FireWire-Bus läuft bereits eine Aufnahme. Parallele Aufnahmen benötigen getrennte Controller.',
    'A capture is already running on this FireWire bus.': 'An diesem FireWire-Bus läuft bereits eine Aufnahme.',
    'Camera disconnected.': 'Kamera getrennt.',
    'No read/write access to ': 'Kein Lese-/Schreibzugriff auf ',
    'FireWire controller not mapped. Rescan devices.': 'FireWire-Controller nicht zugeordnet. Geräte erneut suchen.',
    'At least 2 GiB of free space is required (DV uses about 13 GB/hour).':
        'Mindestens 2 GiB freier Speicherplatz erforderlich (DV benötigt etwa 13 GB pro Stunde).',
    'Less than 512 MiB free. Capture stopped to protect your data.':
        'Weniger als 512 MiB frei. Die Aufnahme wurde zum Schutz deiner Daten beendet.',
    ' Open Setup to enable FireWire access.': ' Über „Einrichtung“ den FireWire-Zugriff aktivieren.',
    'No DV data received. Check PLAYER/VCR mode and PLAY.': 'Keine DV-Daten empfangen. PLAYER/VCR-Modus und PLAY prüfen.',
    'Camera disconnected. Partial capture is kept.': 'Kamera getrennt. Die Teilaufnahme bleibt erhalten.',
    'Signal lost: no new DV data for 30 seconds. Check manually whether the tape has ended.':
        'Signal verloren: Seit 30 Sekunden treffen keine DV-Daten ein. Prüfe, ob das Band zu Ende ist.',
    'dvgrab is missing. Install it through Setup.': 'dvgrab fehlt. Installiere es über „Einrichtung“.',
    'Connect only one camera per FireWire bus in manual mode.':
        'Im manuellen Modus darf nur eine Kamera pro FireWire-Bus angeschlossen sein.',
    'The original camera is not connected. Connect it over FireWire and rescan.':
        'Die ursprüngliche Kamera ist nicht verbunden. Per FireWire anschließen und Geräte erneut suchen.',
    'This tape has no interrupted capture to continue.': 'Für diese Kassette gibt es keine unterbrochene Aufnahme zum Fortsetzen.',
    'Only interrupted or incomplete captures can be continued.':
        'Nur unterbrochene oder unvollständige Aufnahmen können fortgesetzt werden.',
    'No partial DV capture is available to continue.': 'Keine teilweise DV-Aufnahme zum Fortsetzen vorhanden.',
    'This job cannot be queued again': 'Dieser Auftrag kann nicht erneut eingereiht werden.',
    'No raw file available': 'Keine Rohdatei verfügbar.',
    'No valid video output': 'Keine gültige Videoausgabe.',
    'Output duration does not match the source': 'Die Ausgabedauer stimmt nicht mit der Quelle überein.',
    'Resolution or aspect ratio changed': 'Auflösung oder Seitenverhältnis wurden verändert.',
    'Audio streams, channels or sample rate missing/changed': 'Tonspuren, Kanäle oder Abtastrate fehlen oder wurden verändert.',
    'Raw file is missing or empty': 'Rohdatei fehlt oder ist leer.',
    'Raw capture contains no valid video': 'Die Rohaufnahme enthält kein gültiges Video.',
    'Raw file changed during conversion': 'Die Rohdatei wurde während der Konvertierung verändert.',
    'Output completed; original kept: ': 'Ausgabe abgeschlossen; Original wurde behalten: ',
    'Cannot read queue: ': 'Warteschlange kann nicht gelesen werden: ',
    'Invalid queue': 'Ungültige Warteschlange.', 'Invalid job': 'Ungültiger Auftrag.',
    'Stop or finish this tape before removing it from history.':
        'Beende diese Kassette, bevor du sie aus dem Verlauf entfernst.',
    'Original DV capture is missing': 'Die originale DV-Aufnahme fehlt.',
    'No resumed DV segments were found': 'Keine fortgesetzten DV-Abschnitte gefunden.',
    'No available tape number': 'Keine freie Kassettennummer verfügbar.',
    'Yes': 'Ja', 'No': 'Nein',
    'Unsafe raw file path; original kept': 'Unsicherer Rohdateipfad; Original wurde behalten.',
    'Verified output missing; original kept': 'Geprüfte Ausgabe fehlt; Original wurde behalten.',
    'File changed since verification; original kept': 'Datei wurde seit der Prüfung verändert; Original wurde behalten.',
    'Current capture': 'Aktuelle Aufnahme', 'Cancel all': 'Alles abbrechen',
    'Click to stop the active capture and start conversion.': 'Klicken, um die Aufnahme zu beenden und die Konvertierung zu starten.',
    'Start recording from the selected camera.': 'Aufnahme mit der ausgewählten Kamera starten.',
    'Stop all active captures and the current conversion. Queued jobs will remain queued.':
        'Alle laufenden Aufnahmen und die aktuelle Konvertierung beenden. Wartende Aufträge bleiben in der Warteschlange.',
    'Stop all active captures and the current conversion? Partial recordings will be kept; queued jobs will remain queued.':
        'Alle laufenden Aufnahmen und die aktuelle Konvertierung abbrechen? Teilaufnahmen bleiben erhalten; wartende Aufträge bleiben in der Warteschlange.',
    'Stopping…': 'Wird beendet …',
    'Choose the camera to use and check that device access is ready.':
        'Kamera auswählen und prüfen, ob der Gerätezugriff bereit ist.',
    'Set the tape name and destination, then review the capture options.':
        'Kassettenname und Speicherort festlegen und die Aufnahmeeinstellungen prüfen.',
    'Choose the output format and quality used after capture.':
        'Ausgabeformat und Qualität für die anschließende Konvertierung auswählen.',
}
