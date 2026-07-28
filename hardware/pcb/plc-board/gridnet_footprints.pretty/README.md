Project-local footprint library for the PLC/Power Board — same purpose as
the Main Board's `gridnet_footprints.pretty/`: parts not in KiCad's
bundled libraries.

`ESP32-C3-MINI-1.kicad_mod`
---------------------------

Vendored unmodified from Espressif's official KiCad library:
https://github.com/espressif/kicad-libraries, `footprints/Espressif.pretty/ESP32-C3-MINI-1.kicad_mod`,
commit current as of 2026-07-26.

License: [CC-BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/legalcode),
same terms as the Main Board's vendored MINI-1U footprint (see that
directory's README.md) and as every part `build_library.py` copies out of
KiCad's own bundled libraries.

Verified before use: 53 distinct pad numbers (identical layout to the
Main Board's MINI-1U footprint, including the pin-49 3x3 thermal-pad
array), matching Table 3-1 of the ESP32-C3-MINI-1/1U datasheet. This
plain (non-U) variant has an on-module PCB antenna; the -1U has an
on-module W.FL/MHF III jack instead. Neither has an RF pad -- the pad
count and layout are the same for both.
