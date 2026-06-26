# Final Submission Package

This directory contains the call-record bundle for the Pretty Good AI hiring challenge.

Calls are grouped by type under call_records/:

- Each type directory may include 00_selected_top_10/ for priority review calls.
- Each type directory includes 01_all_over_60_seconds/ for every local recording of that type verified as longer than 60 seconds.
- CALL_RECORDS_MANIFEST.csv and CALL_RECORDS_MANIFEST.json list every copied record, duration, source, and relative path.

No zip archives are required for the GitHub submission. Metadata copies in this package are sanitized for the Twilio account SID, outbound phone number, and ngrok base URL.
