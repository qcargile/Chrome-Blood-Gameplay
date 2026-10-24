# Chrome & Blood Gameplay

The native Chrome & Blood installation uses two separate sources:

- The Nexus Collection contains original Nexus mod files.
- This GitHub repository catalogs the separate C&B launcher supplement: custom gameplay, settings, overrides and integration helpers.

The C&B installer combines the original Nexus downloads with the matching GitHub files using a signed release. These working snapshots are component packages, not a complete modlist.

The new installer and release feed are in private testing. For the current public release, use the [installation guide](https://qcargile.github.io/Chrome-Blood/install.html). This repository is also the planned home for the single Windows installer EXE and its signed release feed.

When the installer is publicly released, its download will include the exact EXE's SHA-256 checksum and a matching VirusTotal report link. The report shows the scan date and engine results; it is not a guarantee of safety. There is no public native installer download or VirusTotal report for it here yet.

This is an unofficial fan work and is not approved or endorsed by CD PROJEKT RED. The files are free and are not paywalled.

## Gameplay snapshot

[Download the working gameplay snapshot](https://github.com/qcargile/Chrome-Blood-Gameplay/releases/download/working-b88ca53afd5e/Chrome-Blood-Gameplay-b88ca53afd5e.zip)

- SHA-256: `b88ca53afd5e5485791f8ea43ffe63f4236aee111fd10a1bde24a364fc360151`
- Size: 252,785 bytes
- Files: 117 unchanged payload files and a credits notice

The archive includes current C&B gameplay/settings and LUT Switcher/HUD Painter overrides. It excludes local metadata, logs and runtime state. It is a working snapshot, not a numbered modlist release.

## Other C&B files

- [Compatibility](https://github.com/qcargile/Chrome-Blood-Compatibility/releases/tag/v1.0.0)
- [Dark Future patch](https://github.com/qcargile/Chrome-Blood-Dark-Future-Patch/releases/tag/v1.0.0)
- [Limited HUD patch](https://github.com/qcargile/Chrome-Blood-Limited-HUD-Patch/releases/tag/v1.0.0)
- [Conflict Studio 1.0.1 pinned support build](https://github.com/qcargile/Cyberpunk-Conflict-Studio/releases/tag/v1.0.1)

`packages.json` records exact asset hashes and locations. `gameplay-files.json` records the gameplay archive contents. `THIRD_PARTY_NOTICES.md` credits the original mod authors. The two helpers under `tools/mo2` are licensed under GPLv3; that license does not apply to the separate launcher or to the gameplay archive.

The earlier Collection-member example was removed because C&B supplemental files are separate from the Nexus Collection. No Nexus Collection revision was published or changed by this repository.

## FOMOD resolver source

[The FOMOD resolver](tools/fomod/README.txt) applies the list's recorded installer choices. Its C&B scripts are licensed under GPLv3. The matching Nexus Mods FOMOD 0.13.4 source, build inputs, dependency source and license texts are included under `tools/fomod`.

This component's license does not select a license for the separate launcher or NXM relay. These are source materials for the installer; players do not need to install them manually.

## Patches and overrides

[Download the working patches](<https://github.com/qcargile/Chrome-Blood-Gameplay/releases/download/working-0ba0ec762a44/Chrome-Blood-Patches-0ba0ec762a44.zip>)

This archive contains 280 C&B patches and custom files for 55 mod entries. It is separate from the Nexus Collection. The launcher downloads the original mods and applies these changes using the signed release recipe; this ZIP is not a standalone modlist.

- SHA-256: `0ba0ec762a44d6d77999232fb2f8d560f2d70aa7c4ee6cfbe31871558d78b1e2`
- Size: 549,328 bytes
- Contents: 190 binary patches and 90 inline files
- [Changed files and required original archives](<https://github.com/qcargile/Chrome-Blood-Gameplay/releases/download/working-0ba0ec762a44/patches-files.json>)

PDB debug symbols, local metadata, logs, saves and excluded runtime state are omitted. Gameplay and configuration changes are retained. This is a working snapshot for launcher testing.
