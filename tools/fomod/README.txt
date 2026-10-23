Chrome & Blood FOMOD resolver source

resolve.mjs and resolve_collection.mjs are Copyright 2026 Quentin Cargile and are distributed under GPL-3.0. COPYING.txt contains the license. The package and lockfile identify the exact runtime dependencies. The fixture is an input to the resolver and is included with its source.

source/fomod-installer-af3c8355.zip is the full Nexus Mods source tree at commit af3c8355b2e22f1c7c4272c8eb3cb928ccb5f8c1 for @nexusmods/fomod-installer-native 0.13.4. Its native binaries in the Chrome & Blood FOMOD runtime match the official npm tarball for that version. The archive contains the C# Native AOT implementation, Node binding source, build scripts, root pnpm lockfile, and upstream GPL-3.0 license.

source/node-gyp-build-4.8.4.tgz contains the exact npm package source and MIT license for the resolver's other runtime dependency.

To prepare the C&B resolver from this directory, use Node.js 22 or newer and npm ci against package-lock.json. The upstream native package requires .NET 9 SDK, pnpm 10.8.1, and the build process documented in its source archive if rebuilding its native binaries. The source archives are distributed here with this resolver so they remain available with the matching C&B release. This license scope covers the resolver component; it does not license the separate C&B launcher or NXM relay.
