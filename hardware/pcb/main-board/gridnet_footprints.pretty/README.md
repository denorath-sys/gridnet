Project-local footprint library — parts not in KiCad's bundled
libraries, so they can't be extracted programmatically the way
`kicad_gen/build_library.py`'s other real parts are.

`ESP32-C3-MINI-1U.kicad_mod`
----------------------------

Vendored unmodified from Espressif's official KiCad library:
https://github.com/espressif/kicad-libraries, `footprints/Espressif.pretty/ESP32-C3-MINI-1U.kicad_mod`,
commit current as of 2026-07-26.

License: [CC-BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/legalcode)
(with the same use-in-a-design carve-out KiCad's own official libraries
use — see that repo's `LICENSE.md`), the same terms already implicitly
relied on for every part `build_library.py` copies out of KiCad's
bundled libraries.

Replaces the earlier `RF_Module:ESP32-C3-WROOM-02U` placeholder this
design used before datasheet verification — see
`hardware/pcb/main-board/README.md`'s "Per-part confidence levels" and
"Datasheet verification results" for that history. Verified against the
ESP32-C3-MINI-1/1U datasheet (v2.2) before use: 53 distinct pad numbers,
pad 49 (GND) present as the expected 3x3 array of thermal-pad vias under
the module, matching Table 3-1's pin definitions.
