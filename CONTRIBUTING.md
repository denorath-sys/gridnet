# Contributing to GRIDNET

Thank you for your interest in GRIDNET. This is an open hardware project at the design stage — contributions of all kinds are welcome, from hardware expertise to firmware development to documentation improvements.

---

## What We Need Most Right Now

| Area | What's Needed |
|---|---|
| **Hardware / PCB** | Review of schematics, PCB layout, component selection |
| **ST7580 / PLC** | Real-world field experience with powerline communication |
| **Firmware** | Zephyr RTOS, RISC-V BSP, ST7580 driver development |
| **Forth VM** | Interpreter implementation, standard library design |
| **Testing** | Anyone willing to run a node in their building |
| **Documentation** | Translations, corrections, improvements |

---

## Ways to Contribute

### Report a Problem or Ask a Question → Open an Issue

If you find an error in the documentation, a problem in the hardware design, or want to ask a technical question:

1. Go to the [Issues tab](../../issues)
2. Click **New Issue**
3. Choose the appropriate label:
   - `hardware` — schematic, PCB, component questions
   - `firmware` — software architecture, Zephyr, drivers
   - `protocol` — communication stack, mesh routing
   - `documentation` — errors, improvements, translations
   - `question` — general questions

Please be specific. Include which document or section you're referring to.

---

### Suggest a Change → Open a Pull Request

If you want to improve documentation, fix an error, or add content:

1. **Fork** the repository (top right → Fork)
2. Create a new branch with a descriptive name:
   ```
   git checkout -b fix/plc-protection-circuit
   git checkout -b docs/turkish-translation
   git checkout -b hardware/pcb-layout-review
   ```
3. Make your changes
4. Commit with a clear message:
   ```
   git commit -m "fix: correct MOV part number in BOM"
   git commit -m "docs: add Turkish translation for protocol.md"
   git commit -m "hardware: add decoupling caps to ST7580 schematic notes"
   ```
5. Push and open a Pull Request
6. Describe what you changed and why

---

### Hardware Review

If you have experience with PLC hardware, embedded systems, or PCB design and want to review the schematics:

- All hardware documentation is in the `hardware/` folder
- Open an Issue with the `hardware` label
- Share your findings as comments or as a Pull Request to the relevant `.md` files

---

### Field Testing

If you want to test GRIDNET concepts with existing PLC hardware (e.g. HomePlug adapters, ST7580 development boards):

- Open an Issue with the label `testing`
- Describe your setup (hardware, building type, distance)
- Any real-world PLC performance data is extremely valuable

---

## Commit Message Format

Please use this format for commit messages:

```
type: short description

Types:
  fix      — corrects an error
  docs     — documentation changes
  hardware — hardware design changes
  firmware — firmware/software changes
  protocol — protocol stack changes
  chore    — maintenance, formatting
```

Examples:
```
fix: correct IRF540 gate resistor value in BOM
docs: add FAQ section to electrical-safety.md
hardware: update protection circuit notes for MOV rating
protocol: clarify MASTER_ALIVE timeout behavior
```

---

## Code of Conduct

- Be respectful and constructive
- Technical disagreements are welcome — personal attacks are not
- This is a collaborative project, not a competition

---

## License

By contributing to GRIDNET, you agree that your contributions will be licensed under the same license as the project:

- Hardware designs and documentation: [CERN-OHL-W-2.0](LICENSE)
- Firmware (when released): GPL-3.0

---

## Questions?

Open an Issue with the `question` label. There are no stupid questions — especially about powerline communication, which is a genuinely obscure topic.

---

*Thank you for helping build something that works when everything else fails.*
