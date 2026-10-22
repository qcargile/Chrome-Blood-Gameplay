# Chrome & Blood Gameplay

Chrome & Blood has two separate sources:

- The Nexus Collection contains original Nexus mod files.
- This GitHub repository catalogs the separate C&B launcher supplement: custom gameplay, settings, overrides and integration helpers.

The launcher is responsible for acquiring and applying both sources. Players should not need to gather the supplemental files one by one. This catalog is not a complete modlist, a Nexus Collection manifest or a signed installation/update recipe. The next signed launcher release must bind these assets before automatic acquisition can use them.

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
