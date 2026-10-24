import hashlib
import json
import os
import stat
import subprocess
from datetime import date
from pathlib import Path, PurePosixPath

import mobase
from PyQt6.QtCore import QCoreApplication, QProcess, QTimer


MAXIMUM_REQUEST_BYTES = 16 * 1024 * 1024
MAXIMUM_FILE_BYTES = 4 * 1024 * 1024 * 1024
MAXIMUM_ARCHIVE_BYTES = 5 * 1024 * 1024 * 1024
SUPPORTED_SEPARATOR_COLOR = r"@Variant(\0\0\0\x43\x1\xff\xff\x31\x31\0\0\0\0\0\0)"
PREINSTALLED_MODE = "preinstalled"
MAXIMUM_NOTICE_OUTPUT_BYTES = 4096
MAXIMUM_HOST_STATE_BYTES = 16 * 1024 * 1024
NOTICE_CAPABILITY_PATH = "resources/capabilities/mo2-release-notice.json"


def request_install_mode(request):
    if request.get("schemaVersion") != 1:
        raise ValueError("collection.request-schema")
    mode = request.get("installMode")
    if mode is None:
        return "legacy"
    if mode != PREINSTALLED_MODE:
        raise ValueError("collection.install-mode")
    return mode


def category_line(item):
    category = item.get("category")
    if category is None:
        return None
    primary = category.get("primaryId")
    additional = category.get("additionalIds")
    if type(primary) is not int or primary not in (-1, 0) and not 1 <= primary <= 17 or not isinstance(additional, list):
        raise ValueError("collection.category")
    previous = 0
    for value in additional:
        if type(value) is not int or not 1 <= value <= 17 or value == primary or value <= previous:
            raise ValueError("collection.category")
        previous = value
    if primary <= 0 and additional:
        raise ValueError("collection.category")
    return "category=0" if primary == 0 else f'category="{primary},{",".join(str(value) for value in additional)}"'


def physical(path):
    value = Path(path).absolute()
    for item in [value, *value.parents]:
        if os.lstat(extended(item)).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("collection.reparse-path")
    return value


def extended(path):
    value = str(Path(path).absolute())
    if value.startswith("\\\\?\\"):
        return value
    if value.startswith("\\\\"):
        return "\\\\?\\UNC\\" + value[2:]
    return "\\\\?\\" + value


def file_size(path):
    return os.stat(extended(path)).st_size


def read_bytes(path, maximum):
    item = physical(path)
    size = file_size(item)
    if size > maximum:
        raise ValueError("collection.file-bound")
    with open(extended(item), "rb") as stream:
        return stream.read(maximum + 1)


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def strict_json(value):
    def distinct(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("collection.duplicate-json-key")
            result[key] = item
        return result
    return json.loads(value.decode("utf-8"), object_pairs_hook=distinct)


def valid_hash(value):
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def valid_id(value):
    return isinstance(value, str) and 0 < len(value) <= 128 and value not in (".", "..") \
        and not value.endswith(".") and all(
        character.isascii() and (character.isalnum() or character in "-._") for character in value)


def trusted_chrome_blood_host():
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data or not Path(local_app_data).is_absolute():
        return None
    app = Path(local_app_data) / "ChromeAndBlood" / "app"
    pointer_bytes = read_bytes(app / "current.json", MAXIMUM_NOTICE_OUTPUT_BYTES)
    pointer = strict_json(pointer_bytes)
    release_id = pointer.get("releaseId")
    installed_hash = pointer.get("installedReleaseSha256")
    if pointer.get("schemaVersion") != 1 or not valid_id(release_id) or not valid_hash(installed_hash):
        return None
    installed_bytes = read_bytes(app / "installed-releases" / f"{release_id}.json", MAXIMUM_HOST_STATE_BYTES)
    if sha256(installed_bytes) != installed_hash:
        return None
    installed = strict_json(installed_bytes)
    manifest_hash = installed.get("hostPackageManifestSha256")
    if installed.get("schemaVersion") != 2 or installed.get("releaseId") != release_id \
            or installed.get("slotRelativePath") != f"releases/{release_id}" or not valid_hash(manifest_hash):
        return None
    host_root = app / "releases" / release_id / "payload" / "host"
    manifest_bytes = read_bytes(host_root / "package-manifest.json", MAXIMUM_HOST_STATE_BYTES)
    if sha256(manifest_bytes) != manifest_hash:
        return None
    manifest = strict_json(manifest_bytes)
    files = manifest.get("files")
    if manifest.get("schemaVersion") != 1 or manifest.get("selfContained") is not True \
            or not isinstance(files, list) or not 1 <= len(files) <= 4096:
        return None
    executable = [item for item in files if isinstance(item, dict)
                  and item.get("path", "").casefold() == "chromeblood.exe"]
    capability = [item for item in files if isinstance(item, dict)
                  and item.get("path", "").casefold() == NOTICE_CAPABILITY_PATH]
    if len(executable) != 1 or type(executable[0].get("size")) is not int \
            or executable[0]["size"] <= 0 or not valid_hash(executable[0].get("sha256")):
        return None
    if len(capability) != 1 or type(capability[0].get("size")) is not int \
            or not 0 < capability[0]["size"] <= MAXIMUM_NOTICE_OUTPUT_BYTES \
            or not valid_hash(capability[0].get("sha256")):
        return None
    host = physical(host_root / "ChromeBlood.exe")
    if file_size(host) != executable[0]["size"] or digest(host) != executable[0]["sha256"]:
        return None
    capability_path = physical(host_root / NOTICE_CAPABILITY_PATH)
    capability_bytes = read_bytes(capability_path, MAXIMUM_NOTICE_OUTPUT_BYTES)
    if len(capability_bytes) != capability[0]["size"] or sha256(capability_bytes) != capability[0]["sha256"]:
        return None
    declaration = strict_json(capability_bytes)
    if set(declaration) != {"schemaVersion", "protocol", "commands"} \
            or declaration["schemaVersion"] != 1 or declaration["protocol"] != 1 \
            or declaration["commands"] != ["mo2-release-notice-check", "open-updates"]:
        return None
    return host


def physical_files(root):
    normal = physical(root)
    extended_root = extended(normal)
    files = []
    for directory, directories, names in os.walk(extended_root):
        for name in directories:
            if os.lstat(os.path.join(directory, name)).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError("collection.reparse-path")
        for name in names:
            path = os.path.join(directory, name)
            if os.lstat(path).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError("collection.reparse-path")
            files.append(os.path.relpath(path, extended_root).replace("\\", "/"))
    return sorted(files)


def relative(value):
    if not isinstance(value, str) or not value or len(value) > 512 or "\\" in value or ":" in value or value.startswith("/"):
        raise ValueError("collection.invalid-relative-path")
    parts = value.split("/")
    if any(part in ("", ".", "..") or part.endswith((".", " ")) for part in parts):
        raise ValueError("collection.invalid-relative-path")
    return PurePosixPath(value)


def digest(path, maximum=MAXIMUM_FILE_BYTES):
    item = physical(path)
    details = os.stat(extended(item))
    if not stat.S_ISREG(details.st_mode) or details.st_size > maximum:
        raise ValueError("collection.file-bound")
    with open(extended(item), "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def tree_files(tree):
    files = []
    def visit(path, entry):
        if entry.isFile():
            files.append(f"{path}{entry.name()}".lstrip("/").replace("\\", "/"))
        return mobase.IFileTree.WalkReturn.CONTINUE
    tree.walk(visit, "/")
    return sorted(files)


class CuratedTreeInstaller(mobase.IPluginInstallerSimple):
    def __init__(self):
        super().__init__()
        self._root = None
        self._mods = []
        self._current = None

    def name(self):
        return "Chrome & Blood Curated Tree Installer"

    def author(self):
        return "Chrome & Blood"

    def description(self):
        return "Accepts exact file trees from one pinned private Collection request."

    def version(self):
        return mobase.VersionInfo(0, 1, 0)

    def settings(self):
        return []

    def init(self, organizer):
        self._root = Path(organizer.basePath()).absolute()
        request_path = self._root / "cb-collection-request.json"
        try:
            if os.path.exists(extended(self._root / "cb-collection-result.json")):
                return True
            request = json.loads(read_bytes(request_path, MAXIMUM_REQUEST_BYTES).decode("utf-8"))
            self._mods = [] if request_install_mode(request) == PREINSTALLED_MODE else request["mods"]
        except FileNotFoundError:
            pass
        return True

    def priority(self):
        return 10000

    def isManualInstaller(self):
        return False

    def onInstallationStart(self, archive, reinstallation, current_mod):
        archive_path = Path(archive).absolute()
        self._current = next((item for item in self._mods if Path(item["archivePath"]).absolute() == archive_path and digest(archive_path, MAXIMUM_ARCHIVE_BYTES) == item["archiveSha256"]), None)

    def onInstallationEnd(self, result, new_mod):
        self._current = None

    def isArchiveSupported(self, tree):
        files = tree_files(tree)
        candidates = [self._current] if self._current else self._mods
        return any(item is not None and files == sorted(file["path"] for file in item["files"]) for item in candidates)

    def install(self, name, tree, version, nexus_id):
        files = tree_files(tree)
        if self._current is None or files != sorted(file["path"] for file in self._current["files"]):
            return mobase.InstallResult.FAILED
        return tree


class CollectionInstaller(mobase.IPlugin):
    def __init__(self):
        super().__init__()
        self._organizer = None
        self._window = None
        self._root = None
        self._request = None
        self._request_hash = None
        self._pending = []
        self._installed_names = []
        self._profile_entries = []
        self._next_refresh_callback = None

    def name(self):
        return "Chrome & Blood Collection Installer"

    def author(self):
        return "Chrome & Blood"

    def description(self):
        return "Installs one pinned private Collection request."

    def version(self):
        return mobase.VersionInfo(0, 1, 0)

    def settings(self):
        return []

    def init(self, organizer):
        self._organizer = organizer
        self._root = Path(organizer.basePath()).absolute()
        if os.path.isfile(extended(self._root / "cb-collection-request.json")) and not os.path.exists(extended(self._root / "cb-collection-result.json")):
            organizer.onUserInterfaceInitialized(self._ready)
        return True

    def _ready(self, window):
        self._window = window
        window.hide()
        QTimer.singleShot(0, self._start)

    def _start(self):
        try:
            request_path = physical(self._root / "cb-collection-request.json")
            request_bytes = read_bytes(request_path, MAXIMUM_REQUEST_BYTES)
            self._request_hash = hashlib.sha256(request_bytes).hexdigest()
            if read_bytes(self._root / "cb-collection-request.sha256", 64).decode("ascii") != self._request_hash:
                raise ValueError("collection.request-hash")
            request = json.loads(request_bytes.decode("utf-8"))
            self._request = request
            install_mode = request_install_mode(request)
            if Path(request["instanceRoot"]).absolute() != self._root:
                raise ValueError("collection.instance-binding")
            if self._organizer.profile().name() != request["profileName"]:
                raise ValueError("collection.profile-binding")
            if Path(self._organizer.profile().absolutePath()).absolute() != self._root / "profiles" / request["profileName"]:
                raise ValueError("collection.profile-path")
            if Path(self._organizer.modsPath()).absolute() != self._root / "mods":
                raise ValueError("collection.mods-path")
            if self._organizer.managedGame().gameShortName() != "cyberpunk2077":
                raise ValueError("collection.game")
            if Path(self._organizer.managedGame().gameDirectory().absolutePath()).absolute() != Path(request["gameRoot"]).absolute():
                raise ValueError("collection.game-path")
            mods = request["mods"]
            if not isinstance(mods, list) or not mods or len(mods) > 4096:
                raise ValueError("collection.mod-count")
            priorities = [item["priority"] for item in mods]
            if len(set(priorities)) != len(priorities):
                raise ValueError("collection.priority-collision")
            entries = request.get("profileEntries")
            if entries is None:
                entries = [{"name": item["name"], "separator": False, "enabled": item["enabled"]}
                           for item in sorted(mods, key=lambda item: item["priority"])]
            if not isinstance(entries, list) or not entries or len(entries) > 4096:
                raise ValueError("collection.profile-entry-count")
            if any(item.get("category") is not None for item in entries):
                categories = read_bytes(self._root / "categories.dat", 2 * 1024 * 1024).decode("utf-8").splitlines()
                ids = []
                for line in categories:
                    parts = line.split("|")
                    if len(parts) != 3 or not parts[0].isdigit() or not parts[2].isdigit() or not parts[1]:
                        raise ValueError("collection.category-schema")
                    ids.append(int(parts[0]))
                if sorted(ids) != list(range(1, 18)):
                    raise ValueError("collection.category-schema")
            names = [item["name"] for item in entries]
            if len(set(name.casefold() for name in names)) != len(names):
                raise ValueError("collection.profile-duplicate")
            expected_mods = {item["name"]: item for item in mods}
            if {item["name"] for item in entries if not item["separator"] and not item.get("empty", False)} != set(expected_mods):
                raise ValueError("collection.profile-members")
            for priority, item in enumerate(entries):
                category_line(item)
                if item["separator"]:
                    if item.get("empty", False) or not item["name"].lower().endswith("_separator") or item.get("separatorColor") != SUPPORTED_SEPARATOR_COLOR:
                        raise ValueError("collection.separator-metadata")
                elif item.get("empty", False):
                    if item["enabled"] or item["name"] in expected_mods or item["name"].lower().endswith("_separator") or item.get("separatorColor") is not None:
                        raise ValueError("collection.empty-profile-mod")
                elif item["name"] not in expected_mods or item["enabled"] != expected_mods[item["name"]]["enabled"] or priority != expected_mods[item["name"]]["priority"]:
                    raise ValueError("collection.profile-state")
            self._profile_entries = entries
            if install_mode == PREINSTALLED_MODE:
                self._installed_names = names
                QTimer.singleShot(0, self._verify_profile)
            else:
                self._pending = sorted(mods, key=lambda item: item["priority"])
                QTimer.singleShot(0, self._install_next)
        except Exception as error:
            self._finish_failure(error)

    def _install_next(self):
        try:
            if not self._pending:
                self._install_profile_folders()
                return
            details = self._pending.pop(0)
            name = details["name"]
            archive = physical(details["archivePath"])
            if digest(archive, MAXIMUM_ARCHIVE_BYTES) != details["archiveSha256"]:
                raise ValueError("collection.payload-archive")
            existing = self._organizer.modList().getMod(name)
            if existing is not None:
                self._verify_installed(details)
                self._installed_names.append(name)
                del existing
                QTimer.singleShot(0, self._install_next)
                return
            previous = self._organizer.pluginSetting("Simple Installer", "silent")
            try:
                self._organizer.setPluginSetting("Simple Installer", "silent", True)
                mod = self._organizer.installMod(str(archive), name)
            finally:
                self._organizer.setPluginSetting("Simple Installer", "silent", previous)
            if mod is None or mod.name() != name or Path(mod.absolutePath()).absolute() != self._root / "mods" / name:
                raise ValueError("collection.install-return")
            self._verify_installed(details)
            mod.setGameName("cyberpunk2077")
            mod.setVersion(mobase.VersionInfo(details["version"]))
            source_type = details.get("sourceType") or "nexus"
            source = {"installationFile": details["installationFile"], "sourceType": source_type}
            if source_type == "nexus":
                mod.setNexusID(details["modId"])
                mod.setUrl(f"https://www.nexusmods.com/cyberpunk2077/mods/{details['modId']}")
                source["collectionFileId"] = details["fileId"]
            elif source_type == "direct":
                mod.setUrl(details["sourceUrl"])
                source["sourceUrl"] = details["sourceUrl"]
            elif source_type != "generated":
                raise ValueError("collection.source-type")
            if not mod.setPluginSetting(self.name(), "source", json.dumps(source, sort_keys=True, separators=(",", ":"))):
                raise ValueError("collection.source-metadata")
            self._organizer.modDataChanged(mod)
            del mod
            self._installed_names.append(name)
            QTimer.singleShot(0, self._install_next)
        except Exception as error:
            self._finish_failure(error)

    def _install_profile_folders(self):
        try:
            for entry in self._profile_entries:
                if not entry["separator"] and not entry.get("empty", False):
                    continue
                name = entry["name"]
                root = self._root / "mods" / name
                existing = self._organizer.modList().getMod(name)
                if existing is None:
                    created = self._organizer.createMod(name)
                    if created is None or created.name() != name or Path(created.absolutePath()).absolute() != root:
                        raise ValueError("collection.separator-create")
                    if entry["separator"]:
                        metadata = physical(root / "meta.ini")
                        content = "[General]\r\ngameName=cyberpunk2077\r\ncolor=" + entry["separatorColor"] + "\r\n"
                        if category_line(entry) is not None:
                            content += category_line(entry) + "\r\n"
                        with open(extended(metadata), "wb") as stream:
                            stream.write(content.encode("utf-8"))
                        self._organizer.modDataChanged(created)
                    del created
                else:
                    del existing
                if entry["separator"]:
                    self._verify_separator(entry)
                else:
                    self._verify_empty(entry)
                self._installed_names.append(name)
            self._schedule_refresh(self._activate)
        except Exception as error:
            self._finish_failure(error)

    def _verify_separator(self, entry):
        root = self._root / "mods" / entry["name"]
        if physical_files(root) != ["meta.ini"]:
            raise ValueError("collection.separator-files")
        metadata = read_bytes(root / "meta.ini", 1024 * 1024).decode("utf-8")
        if "color=" + entry["separatorColor"] not in metadata.splitlines() or "gameName=cyberpunk2077" not in metadata.splitlines():
            raise ValueError("collection.separator-metadata")
        expected = category_line(entry)
        if expected is not None:
            observed = [line for line in metadata.splitlines() if line.lower().startswith("category=")]
            if len(observed) != 1 or observed[0] != expected and not (entry["category"]["primaryId"] <= 0 and observed[0] in ('category=0', 'category="-1,"')):
                raise ValueError("collection.separator-category")

    def _verify_empty(self, entry):
        root = self._root / "mods" / entry["name"]
        if physical_files(root) != ["meta.ini"] or sorted(os.listdir(extended(root))) != ["meta.ini"]:
            raise ValueError("collection.empty-profile-mod")
        metadata = read_bytes(root / "meta.ini", 1024 * 1024).decode("utf-8").splitlines()
        if [line for line in metadata if line.lower().startswith("modid=")] != ["modid=0"] or [line for line in metadata if line.lower().startswith("installationfile=")] != ["installationFile="]:
            raise ValueError("collection.empty-profile-source")

    def _activate(self):
        try:
            mod_list = self._organizer.modList()
            enabled = [item["name"] for item in self._profile_entries if item["enabled"]]
            if mod_list.setActive(enabled, True) != len(enabled):
                raise ValueError("collection.activation-count")
            disabled = [item["name"] for item in self._profile_entries if not item["enabled"]]
            if disabled and mod_list.setActive(disabled, False) != len(disabled):
                raise ValueError("collection.deactivation-count")
            for priority, item in enumerate(self._profile_entries):
                if not mod_list.setPriority(item["name"], priority):
                    raise ValueError("collection.priority-write")
            QTimer.singleShot(0, lambda: self._schedule_refresh(self._verify_profile))
        except Exception as error:
            self._finish_failure(error)

    def _verify_profile(self):
        try:
            mod_list = self._organizer.modList()
            expected = self._profile_entries
            observed = [name for name in mod_list.allModsByProfilePriority() if name in self._installed_names]
            if observed != [item["name"] for item in expected]:
                raise ValueError("collection.priority-order")
            for priority, item in enumerate(expected):
                active = bool(mod_list.state(item["name"]) & mobase.ModState.ACTIVE)
                observed_priority = mod_list.priority(item["name"])
                if observed_priority != priority or not item["separator"] and active != item["enabled"]:
                    raise ValueError(f"collection.profile-state:{item['name']}:{observed_priority}:{active}:{priority}:{item['enabled']}")
                if item["separator"]:
                    self._verify_separator(item)
                elif item.get("empty", False):
                    self._verify_empty(item)
                else:
                    self._verify_installed(next(mod for mod in self._request["mods"] if mod["name"] == item["name"]))
            expected_modlist = "# This file was automatically generated by Mod Organizer.\r\n" + "\r\n".join(
                ("+" if item["enabled"] else "-") + item["name"] for item in reversed(expected)) + "\r\n"
            profile_path = self._root / "profiles" / self._request["profileName"] / "modlist.txt"
            observed_modlist = read_bytes(profile_path, 4 * 1024 * 1024).decode("utf-8")
            if observed_modlist != expected_modlist:
                observed_lines = observed_modlist.splitlines()[1:]
                expected_lines = expected_modlist.splitlines()[1:]
                mismatch = next((index for index, pair in enumerate(zip(observed_lines, expected_lines)) if pair[0] != pair[1]),
                                min(len(observed_lines), len(expected_lines)))
                actual_line = observed_lines[mismatch] if mismatch < len(observed_lines) else "<missing>"
                expected_line = expected_lines[mismatch] if mismatch < len(expected_lines) else "<missing>"
                raise ValueError(f"collection.profile-modlist:{mismatch}:{actual_line}:{expected_line}")
            for item in self._request["effectiveFiles"]:
                origins = list(self._organizer.getFileOrigins(item["path"]))
                if not origins or origins[0] != item["winner"]:
                    raise ValueError("collection.effective-origin")
            for path in self._request["absentFiles"]:
                if list(self._organizer.getFileOrigins(path)):
                    raise ValueError("collection.absent-origin")
            probe = physical(self._request["vfsProbePath"])
            if digest(probe) != self._request["vfsProbeSha256"]:
                raise ValueError("collection.vfs-probe")
            powershell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
            arguments = subprocess.list2cmdline(["-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(probe), "-RequestSha256", self._request_hash, "-InstanceRoot", str(self._root)])
            launch = {"schemaVersion": 1, "operationId": self._request["operationId"], "requestSha256": self._request_hash, "executable": str(powershell), "arguments": arguments, "workingDirectory": str(self._root), "profileName": self._request["profileName"]}
            launch_bytes = json.dumps(launch, indent=2, ensure_ascii=False).encode("utf-8")
            launch_path = self._root / "cb-collection-vfs-launch.json"
            if os.path.isfile(extended(launch_path)):
                if read_bytes(launch_path, MAXIMUM_REQUEST_BYTES) != launch_bytes:
                    raise ValueError("collection.vfs-launch")
            else:
                with open(extended(launch_path), "xb") as stream:
                    stream.write(launch_bytes)
            handle = self._organizer.startApplication(str(powershell), [arguments], str(self._root), self._request["profileName"])
            if handle == mobase.INVALID_HANDLE_VALUE:
                raise ValueError("collection.vfs-child-start")
            success, exit_code = self._organizer.waitForApplication(handle, False)
            if not success or exit_code != 0:
                diagnostic_path = self._root / "cb-collection-vfs.json"
                detail = "missing-diagnostic"
                if os.path.isfile(extended(diagnostic_path)):
                    diagnostic = json.loads(read_bytes(diagnostic_path, MAXIMUM_REQUEST_BYTES).decode("utf-8-sig"))
                    detail = f"{diagnostic.get('failure')}:{diagnostic.get('errorId')}:line={diagnostic.get('line')}"
                raise ValueError(f"collection.vfs-child:{success}:{exit_code}:{detail}")
            result = {"schemaVersion": 1, "status": "verified", "operationId": self._request["operationId"], "requestSha256": self._request_hash}
            self._write_result(result)
        except Exception as error:
            self._finish_failure(error)

    def _schedule_refresh(self, callback):
        def next_refresh():
            current = self._next_refresh_callback
            self._next_refresh_callback = None
            if current is None:
                raise ValueError("collection.refresh-callback")
            current()
        self._next_refresh_callback = callback
        self._organizer.onNextRefresh(next_refresh, False)
        self._organizer.refresh()

    def _verify_installed(self, details):
        missing, extra = self._installed_file_difference(details)
        if missing or extra:
            raise ValueError(f"collection.installed-file-set:{details['name']}:missing={missing[:4]}:extra={extra[:4]}")
        self._verify_installed_hashes(details)

    def _installed_file_difference(self, details):
        mod_root = physical(self._root / "mods" / details["name"])
        actual = [path for path in physical_files(mod_root) if Path(path).name.casefold() != "meta.ini"]
        expected = sorted(str(relative(item["path"])) for item in details["files"])
        return [path for path in expected if path not in actual], [path for path in actual if path not in expected]

    def _verify_installed_hashes(self, details):
        mod_root = physical(self._root / "mods" / details["name"])
        for item in details["files"]:
            path = physical(mod_root / relative(item["path"]))
            if file_size(path) != item["bytes"] or digest(path) != item["sha256"]:
                raise ValueError("collection.installed-file")

    def _finish_failure(self, error):
        result = {"schemaVersion": 1, "status": "failed", "operationId": self._request.get("operationId") if self._request else "", "requestSha256": self._request_hash or "", "failure": f"{type(error).__name__}:{str(error)[:512]}"}
        self._write_result(result)

    def _write_result(self, result):
        try:
            with open(extended(self._root / "cb-collection-result.json"), "x", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(result, indent=2, ensure_ascii=False))
        finally:
            self._next_refresh_callback = None
            QTimer.singleShot(0, self._window.close)


class CollectionReleaseNotice(mobase.IPluginDiagnose):
    PROBLEM_ID = 0

    def __init__(self):
        super().__init__()
        self._organizer = None
        self._root = None
        self._window = None
        self._probe = None
        self._timer = None
        self._stdout = bytearray()
        self._notice = None

    def name(self):
        return "Chrome & Blood Release Notice"

    def author(self):
        return "Chrome & Blood"

    def description(self):
        return "Reports a newer authenticated Chrome & Blood release in Mod Organizer."

    def version(self):
        return mobase.VersionInfo(0, 1, 0)

    def settings(self):
        return []

    def init(self, organizer):
        self._organizer = organizer
        self._root = Path(organizer.basePath()).absolute()
        request = self._root / "cb-collection-request.json"
        result = self._root / "cb-collection-result.json"
        if os.path.isfile(extended(request)) and not os.path.exists(extended(result)):
            return True
        organizer.onUserInterfaceInitialized(self._ready)
        application = QCoreApplication.instance()
        if application is not None:
            application.aboutToQuit.connect(self._cancel_probe)
        return True

    def activeProblems(self):
        return [self.PROBLEM_ID] if self._notice is not None else []

    def shortDescription(self, key):
        self._require_problem(key)
        version, release_date = self._notice
        identity = version if release_date is None else f"{version} - {release_date}"
        return f"A new version of Chrome & Blood is available ({identity})."

    def fullDescription(self, key):
        self._require_problem(key)
        return self.shortDescription(key) + " Open the Chrome & Blood launcher to review the update."

    def hasGuidedFix(self, key):
        self._require_problem(key)
        return True

    def startGuidedFix(self, key):
        self._require_problem(key)
        try:
            host = trusted_chrome_blood_host()
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("collection.release-host") from error
        if host is None:
            raise ValueError("collection.release-host")
        started = QProcess.startDetached(str(host),
                                         ["--open-updates", "--instance-root", str(self._root)],
                                         str(host.parent))
        if isinstance(started, tuple):
            started = started[0]
        if not started:
            raise ValueError("collection.release-launch")

    def _ready(self, window):
        self._window = window
        if hasattr(window, "destroyed"):
            window.destroyed.connect(self._cancel_probe)
        QTimer.singleShot(0, self._start_probe)

    def _start_probe(self):
        if self._probe is not None:
            return
        try:
            host = trusted_chrome_blood_host()
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
            return
        if host is None:
            return
        process = QProcess()
        process.setProgram(str(host))
        process.setArguments(["--mo2-release-notice-check", "--instance-root", str(self._root)])
        process.setWorkingDirectory(str(host.parent))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read_probe_output)
        process.readyReadStandardError.connect(lambda: process.readAllStandardError())
        process.finished.connect(self._probe_finished)
        process.errorOccurred.connect(self._probe_failed)
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(self._probe_timed_out)
        self._probe = process
        self._timer = timer
        self._stdout = bytearray()
        process.start()
        timer.start(12000)

    def _read_probe_output(self):
        process = self._probe
        if process is None:
            return
        self._stdout.extend(bytes(process.readAllStandardOutput()))
        if len(self._stdout) > MAXIMUM_NOTICE_OUTPUT_BYTES:
            self._cancel_probe()

    def _probe_finished(self, exit_code, exit_status):
        process = self._probe
        if process is None:
            return
        self._read_probe_output()
        output = bytes(self._stdout)
        normal = exit_status == QProcess.ExitStatus.NormalExit
        self._release_probe()
        if not normal or exit_code != 0 or not output:
            return
        try:
            result = strict_json(output)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            return
        if not isinstance(result, dict) or result.get("schemaVersion") != 1 \
                or result.get("status") != "update-available" \
                or not isinstance(result.get("installedVersion"), str) \
                or not isinstance(result.get("availableVersion"), str):
            return
        release_date = result.get("releaseDate")
        if release_date is not None:
            if not isinstance(release_date, str):
                return
            try:
                if date.fromisoformat(release_date).isoformat() != release_date:
                    return
            except ValueError:
                return
        self._notice = (result["availableVersion"], release_date)
        self._invalidate()

    def _probe_failed(self, _):
        self._release_probe()

    def _probe_timed_out(self):
        self._cancel_probe()

    def _cancel_probe(self, *_):
        process = self._probe
        if process is not None:
            process.kill()
            process.waitForFinished(1000)
        self._release_probe()

    def _release_probe(self):
        timer = self._timer
        process = self._probe
        self._timer = None
        self._probe = None
        self._stdout = bytearray()
        if timer is not None:
            timer.stop()
            timer.deleteLater()
        if process is not None:
            process.deleteLater()

    def _require_problem(self, key):
        if key != self.PROBLEM_ID or self._notice is None:
            raise IndexError(key)


def createPlugins():
    return [CuratedTreeInstaller(), CollectionInstaller(), CollectionReleaseNotice()]
