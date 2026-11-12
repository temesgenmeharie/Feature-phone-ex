# Technical & Forensic Limitations

1. **Logical Extraction Scope Only**
   - This system performs **logical extraction** via Hayes AT commands over a serial interface.
   - It **does not** recover deleted SMS messages, deleted contacts, deleted call records, or unallocated flash memory blocks.
   - Physical extraction (BootROM/Flasher dump, JTAG, ISP, Chip-off) is outside the scope of v1.

2. **Manufacturer & Firmware Variability**
   - Feature phone vendors (Nokia, Tecno, Itel, Samsung, Spreadtrum/Unisoc, MediaTek, RDA) implement different subsets of GSM 07.07 / 07.05 AT commands.
   - Some devices expose only a basic modem (`AT`, `ATI`) and return `ERROR` or `CME ERROR` for `AT+CPBS`, `AT+CPBR`, or `AT+CMGL`.
   - The system probes capabilities first and explicitly reports `UNSUPPORTED` rather than failing silently or fabricating data.

3. **Call History vs. Network CDRs**
   - Phonebook-style call logs (`AT+CPBS="MC"`, `"RC"`, `"DC"`) typically return only phone number, name (if matched), and record index.
   - Most feature phones do **not** expose call duration, cell tower IDs, IMSI/IMEI per call, or even timestamps via `AT+CPBR`.
   - Therefore, extracted call logs are **not** equivalent to carrier/network Call Detail Records (CDRs). The UI and reports explicitly label `is_cdr_level = False` and display `Unavailable` for unexposed fields.

4. **Handset Memory vs. SIM Storage**
   - `AT+CPBS="SM"` and `AT+CPMS="SM"` read SIM-resident records, whereas `"ME"` reads handset-resident records.
   - Depending on firmware, some phones store SMS or contacts exclusively in handset memory without exposing `"ME"` over AT commands.

5. **SIM Security Mechanisms**
   - If a SIM is PIN-locked (`+CPIN: SIM PIN`), this tool **will not** attempt to bypass or brute-force the PIN. Authorized examiners must unlock the SIM using standard procedures if legally permitted.

6. **Timestamp & Encoding Differences**
   - Older feature phones may use GSM 7-bit default alphabet, UCS2 hex, or local time without timezone offsets. Unparseable or missing timestamps are preserved verbatim in `timestamp_raw` and left `null` in `timestamp_iso`.

