# 🎮 Wii U Fastfile Studio

[![Python Version](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)](https://github.com/)
[![Target Game](https://img.shields.io/badge/Game-Black_Ops_II_(T6)-red.svg)](https://en.wikipedia.org/wiki/Call_of_Duty:_Black_Ops_II)
[![Buy me a Coffee](https://img.shields.io/badge/Support%20My%20Work-Buy%20me%20a%20coffee%20%E2%98%95-chocolate?style=plastic)](https://buymeacoffee.com/tonytrawl)

A comprehensive toolkit and GUI utility for analyzing, modifying, and rebuilding **Black Ops II (T6) Wii U fastfiles (`.ff`)**.

The Wii U build of T6 packages its zones inside a complex, big-endian, signed, and Salsa20-encrypted container. Because legacy PC and console modding tools fail to read or serialize this specific pipeline correctly, this studio provides a pristine, native Wii U codec, a structural integrity validator, and a deeply customized write-path integration built on top of OpenAssetTools (OAT).

---

## 🛠️ Feature Architecture

The core application structures its toolset across six dedicated functional modules:


```

[ Decrypt ] ─── [ Repack ] ─── [ Validate ] ─── [ Zone Editor ] ─── [ OAT: Write ] ─── [ OAT: Dump ]

```

### 🔓 Decrypt & Decompress
Extracts raw, decompressed zone data from production Wii U `.ff` containers. 
* Parses the authenticated `TAff0100` / version **148** big-endian headers.
* Validates the accompanying `PHEEBs71` auth block and 256-byte RSA metadata block.
* Unwinds **four interleaved Salsa20 chunk streams**, handling raw-deflate extraction framed exactly on `0x80000` super-block boundaries.
* Synchronizes the per-fastfile SHA-1 Initialization Vector (IV) chain seeded by the unique zone name.

### 📦 Repack
Re-serializes modified raw zones back into deployment-ready v148 fastfiles with byte-for-byte fidelity.
* Compresses raw zones down into rigid `0x8000` chunk sizes (the hardware-enforced buffer threshold; exceeding this overflows memory and causes hard console freezes).
* Encrypts data through parallel Salsa20 streams using appropriate per-stream IVs.
* Re-establishes strict hardware-matching super-block padding and alignment constraints.

### 🛡️ Structural Validation
Performs deep-packet pre-flight sanity checks against genuine hardware layout policies before pushing payloads to target systems:
* **Memory Blocks:** Verifies `TEMP` remains minimal while persistent asset data maps cleanly to `VIRTUAL`.
* **Graph Traversal:** Validates `XAssetList` follow-pointers, the global script-string table, and all localized asset directory records.
* **Diff Engine:** Supports optional baseline schema comparison against verified retail reference zones.

### 📂 Zone Editor
An interactive physical inspector for compiled assets.
* Scans the data graph to enumerate every compiled script (**GSC/CSC**) and binary **rawfile**.
* Offers granular disk export for structural deconstruction, reverse-engineering, or local modification.
* Supports **in-place asset replacing**. *Note: Because zones function as fixed, sequential pointer graphs, replacements must match original byte lengths exactly to maintain structure without a full database compilation.*

### 🚀 OAT: Write Wii U Zone & Dump
Exposes a custom, extended branch of OpenAssetTools to compile high-level configurations or harvest raw streams:
* Automates complex big-endian write-path transformations directly through the interface.
* Forces extraction via OAT's low-level decompression pipelines, serving as an excellent fallback mechanism when asset dependency graphs cannot be cleanly resolved.

---

## 📱 Companion Application: Wii U FF Editor

Included in the repository is `WiiU_FF_Editor.exe`—a streamlined, single-purpose application tailored for rapid text asset modifications without intermediary steps.

* **Streamlined Pipeline:** Open a `.ff` file directly $\rightarrow$ edits apply via an interactive, multi-tab text editor (featuring line numbers and global text searching) $\rightarrow$ save modifications to automatically patch and repack.
* **Safety Restraints:** A built-in real-time byte meter tracks local allocations. Shorter strings are padded automatically with null terminators; payload sizes exceeding the original allocation boundaries are strictly blocked to prevent structural corruption.
* **Compilation:** Executable builds can be compiled instantly using the included `build_editor.bat` utility.

---

## 🔧 Core Enhancements to OpenAssetTools

Stock OpenAssetTools assumes a little-endian, self-contained PC architecture. To enable complete Wii U operability, this project incorporates an array of low-level patches (controlled dynamically via environment flags):

| Environment Flag | System Section / Modification | Functional Purpose |
| :--- | :--- | :--- |
| `OAT_WRITE_WIIU` | **Big-Endian v148 Writer** | Byte-swaps all fundamental primitives, structural pointers, block configurations, and asset metrics during serialization. |
| *Auto-Detected* | **Wii U Fastfile Reader** | Catches `TAff0100` header magic, binds localized Wii U Salsa20 cipher keys, and forces big-endian graph parsing. |
| *Auto-Remapped* | **Asset-Type Enum Alignment** | Resolves differences in console asset tables, offsetting shifted structural indices and forcing `MAP_ENTS` onto console ID **47**. |
| *Conditional* | **Block-Policy Shifting** | Enforces hardware allocation standards by routing default asset arrays to `VIRTUAL` space while preserving local `TEMP` fields. Prevents buffer overruns. |
| *Auto-Stripped* | **Inline Pixel Elimination** | Zeroes out `GfxImageLoadDef::resourceSize` payloads to isolate heavy textures to external IPAK files while preserving necessary metadata headers. |
| `OAT_RT_PHYS=<hex>` | **Physical Memory Reservation** | Appends strict, fixed `RUNTIME_PHYSICAL` segment allocations directly into output zone headers to emulate retail profiles. |
| `OAT_DROP_GSC`<br>`OAT_STRIP_GSC`<br>`OAT_GSC_DIR` | **Script Transformation Core** | Controls compiler treatment of `scriptparsetree` items, providing drop, stub, or directory substitution behaviors. |
| `OAT_DUMP_ZONE=<file>` | **Stream Interception Dump** | Intercepts processing pipelines to dump naked, raw decompressed bytes to disk before high-level parsing logic executes. |
| `OAT_IGNORE_SIG` | **Signature Verification Bypass** | Silences non-fatal validation errors on modified or unsigned payloads, ensuring unhindered asset loading. |

---

## ⚙️ Environment & Setup

### Requirements
* **Operating System:** Windows
* **Runtime Environment:** Python **3.9+** (Standard library only; no external `pip` dependencies are required for base features).
* **Asset Compilation (Optional):** A valid build of the custom, extended OpenAssetTools `Unlinker.exe` placed inside an `oat\` directory adjacent to the primary module.

### Launching the Studio UI
```bash
python wiiu_ff_studio.py

```

*Alternatively, compile a completely isolated, standalone Windows executable by running the native `build.bat` script (see `USAGE.md` for extended parameters).*

### Headless CLI Usage

For automated pipelines or build environments, headless tools are exposed directly through the command line:

```bash
# Decrypt a retail container
python wiiu_ff.py decrypt <path_to_input.ff>

# Pack a modified zone folder
python wiiu_ff.py pack <path_to_zone_folder> <zone_name>

# Validate structural compliance against a retail reference point
python zone_validate.py <path_to_target_zone> --ref <path_to_genuine_zone>

```

---

## ⚠️ Engineering Constraints

> [!IMPORTANT]
> **Cryptographic Integrity:** The 256-byte RSA signature block requires private keys that remain unavailable. Rebuilt fastfiles write null bytes (`0x00`) across this entire allocation block. Successful deployment requires a console-side loader configured with a signature-check bypass or an unsigned-FF execution path.

> [!WARNING]
> **Hardware-Specific Shaders:** Geometry data compiled for distinct GPU microarchitectures cannot be universally translated. This studio processes structures, container formats, metadata blocks, and graph allocations—it does not re-encode hardware-level vertex arrays or asset shaders.
