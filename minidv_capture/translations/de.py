"""German interface translation."""

CODE = 'de'
NAME = 'Deutsch'
FLAG = '🇩🇪'
STRINGS = {
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
    'Raw footage is kept by default. AVI/DV remuxes without quality loss.\nYou can capture the next tape while conversion runs.':
        'Rohmaterial bleibt standardmäßig erhalten. AVI/DV wird ohne Qualitätsverlust umverpackt.\nWährend der Konvertierung kann die nächste Kassette aufgenommen werden.',
    'Capture request accepted. Waiting for dvgrab to start…': 'Aufnahmeanfrage angenommen. Warte auf den Start von dvgrab …',
    'Camera not found. Check power, PLAYER/VCR mode and FireWire cable, then check devices and retry.':
        'Kamera nicht gefunden. Stromversorgung, PLAYER/VCR-Modus und FireWire-Kabel prüfen, danach Geräte prüfen und erneut versuchen.',
    'dvgrab started; waiting for PLAY': 'dvgrab gestartet; warte auf PLAY',
    'Waiting for DV data (may be rewinding)': 'Warte auf DV-Daten (eventuell wird zurückgespult)',
    'Waiting for DV data': 'Warte auf DV-Daten',
    'DV data arriving; capturing': 'DV-Daten treffen ein; Aufnahme läuft',
    'Stopping capture…': 'Aufnahme wird beendet …',
    'Capture estimate based on 90 minutes. This does not detect the end of the tape.':
        'Aufnahmeschätzung auf Basis von 90 Minuten. Das Kassettenende wird nicht erkannt.',
    'Conversion includes output verification.': 'Die Konvertierung umfasst eine Prüfung der Ausgabe.',
    'Waiting for conversion': 'Wartet auf Konvertierung',
}
