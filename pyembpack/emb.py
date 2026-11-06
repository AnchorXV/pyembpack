from __future__ import annotations

import re
import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, **kwargs):
        return iterable


MAGIC = b"#EMB"
MAGIC_SUFFIX = b"\xfe\xff"
HEADER_SIZE = 0x20
ALIGN = 0x40
DEFAULT_VERSION = "0.0.0.0"


class EMBError(Exception):
    pass


@dataclass
class EMBFile:
    data: bytes
    name: str = ""
    index: int = 0


class EMB:
    def __init__(self) -> None:
        self.version = DEFAULT_VERSION
        self.files: list[EMBFile] = []
        self.debug_have_names = False
        self._had_names = False

    XML_FILENAME = "embFiles.xml"
    MAX_FILE_SIZE = 256 * 1024 * 1024
    MAX_FILE_COUNT = 65535

    # ---- load ----
    def load(self, filename: str | Path) -> "EMB":
        raw = Path(filename).read_bytes()
        if len(raw) < HEADER_SIZE:
            raise EMBError("File is too small to be an EMB file")
        if raw[:4] != MAGIC:
            raise EMBError("Invalid EMB signature")

        header_size = struct.unpack_from("<H", raw, 0x06)[0]
        if header_size < HEADER_SIZE:
            raise EMBError(f"Invalid header size: 0x{header_size:X}")

        version_bytes = raw[0x08:0x0C]
        self.version = ".".join(str(b) for b in version_bytes)

        file_count = struct.unpack_from("<I", raw, 0x0C)[0]
        if file_count > self.MAX_FILE_COUNT:
            raise EMBError(
                f"File count {file_count} exceeds safety limit "
                f"({self.MAX_FILE_COUNT})"
            )
        data_table_address = struct.unpack_from("<I", raw, 0x18)[0]
        filename_table_address = struct.unpack_from("<I", raw, 0x1C)[0]

        if data_table_address + file_count * 8 > len(raw):
            raise EMBError("Data table is outside file bounds")

        self.files = []
        self.debug_have_names = filename_table_address != 0
        self._had_names = self.debug_have_names

        for i in range(file_count):
            rel_offset, size = struct.unpack_from(
                "<II", raw, data_table_address + i * 8
            )
            # offset asli: 0x20 + i*8 + rel_offset
            actual_offset = 0x20 + i * 8 + rel_offset
            if size == 0:
                data = b""
            else:
                if actual_offset + size > len(raw):
                    raise EMBError(f"File entry {i} data is outside file bounds")
                if size > self.MAX_FILE_SIZE:
                    raise EMBError(
                        f"File entry {i} size {size} exceeds safety limit "
                        f"({self.MAX_FILE_SIZE} bytes)"
                    )
                data = raw[actual_offset:actual_offset + size]
            self.files.append(EMBFile(data=data, index=i))

        if filename_table_address:
            if filename_table_address + file_count * 4 > len(raw):
                raise EMBError("Filename table is outside file bounds")
            for i in range(file_count):
                string_address = struct.unpack_from(
                    "<I", raw, filename_table_address + i * 4
                )[0]
                if string_address == 0:
                    continue
                end = raw.find(b"\x00", string_address)
                if end < 0:
                    raise EMBError(f"Filename string {i} has no null terminator")
                self.files[i].name = raw[string_address:end].decode(
                    "utf-8", errors="replace"
                )

        return self

    # ---- save ----
    def save(
        self,
        filename: str | Path,
        enable_filenames: bool = True,
        big_endian: bool = False,
    ) -> None:
        if big_endian:
            raise NotImplementedError("Big-endian EMB save is not implemented yet")

        count = len(self.files)
        buf = bytearray()

        buf += MAGIC
        buf += MAGIC_SUFFIX
        buf += struct.pack("<H", HEADER_SIZE)

        # versi 4 byte
        version_parts = self.version.split(".") if self.version else ["0"]
        for i in range(4):
            if i < len(version_parts) and version_parts[i].isdigit():
                value = int(version_parts[i])
            else:
                value = 0
            buf.append(value & 0xFF)

        buf += struct.pack("<I", count)
        buf += b"\x00" * 8
        buf += b"\x00" * 8

        data_table_address = len(buf)  # 0x20
        buf += b"\x00" * (count * 8)

        string_table_address = 0
        if enable_filenames:
            string_table_address = len(buf)
            buf += b"\x00" * (count * 4)

        for i, file_entry in enumerate(self.files):
            while len(buf) % ALIGN:
                buf.append(0)

            actual_offset = len(buf)
            relative_offset = actual_offset - i * 8 - 0x20
            size = len(file_entry.data)

            if size == 0:
                relative_offset = 0
                size = 0

            buf += file_entry.data
            struct.pack_into(
                "<II", buf, data_table_address + i * 8,
                relative_offset, size,
            )

        if enable_filenames:
            while len(buf) % ALIGN:
                buf.append(0)

            string_offsets: list[int] = []
            for file_entry in self.files:
                string_offsets.append(len(buf))
                buf += file_entry.name.encode("utf-8") + b"\x00"

            for i, offset in enumerate(string_offsets):
                struct.pack_into("<I", buf, string_table_address + i * 4, offset)

        struct.pack_into("<I", buf, 0x18, data_table_address)
        struct.pack_into("<I", buf, 0x1C, string_table_address)

        Path(filename).write_bytes(buf)

    # ---- extract ----
    def extract(self, folder: str | Path, progress: bool = True) -> None:
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)

        used_names: set[str] = set()
        entries: list[tuple[str, str, int]] = []

        iterator: Iterable[EMBFile] = self.files
        if progress:
            iterator = tqdm(self.files, desc=f"Extract {folder.name}")

        for i, file_entry in enumerate(iterator):
            original_name = file_entry.name or self._default_name(i)
            safe_name = self._unique_filename(original_name, used_names)
            (folder / safe_name).write_bytes(file_entry.data)
            entries.append((original_name, safe_name, i))

        self._write_xml(folder, entries)

    def _default_name(self, index: int) -> str:
        if index < 1000:
            width = 3
        elif index < 10000:
            width = 4
        else:
            width = 5
        return f"DATA{index:0{width}d}.dds"

    def _unique_filename(self, name: str, used: set[str]) -> str:
        # hapus karakter invalid Windows
        base = Path(name).name
        base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base)
        if not base:
            base = "file"

        stem = Path(base).stem
        suffix = Path(base).suffix
        candidate = base
        counter = 1
        while candidate.lower() in used:
            candidate = f"{stem}_{counter}{suffix}"
            counter += 1

        used.add(candidate.lower())
        return candidate

    def _write_xml(
        self,
        folder: Path,
        entries: list[tuple[str, str, int]],
    ) -> None:
        root = ET.Element(
            "EMB",
            {
                "version": self.version,
                "debugHaveNames": "true" if self.debug_have_names else "false",
            },
        )

        for name, filename, index in entries:
            ET.SubElement(
                root, "File",
                {"name": name, "filename": filename, "index": str(index)},
            )

        ET.indent(root)
        ET.ElementTree(root).write(
            folder / "embFiles.xml", encoding="utf-8", xml_declaration=True,
        )

    # ---- pack ----
    def add_file(self, filename: str | Path) -> None:
        path = Path(filename)
        if not path.is_file():
            raise EMBError(f"Not a file: {path}")
        self.files.append(EMBFile(
            data=path.read_bytes(), name=path.name, index=len(self.files),
        ))

    def add_folder(self, folder: str | Path) -> None:
        folder = Path(folder)
        if not folder.is_dir():
            raise EMBError(f"Not a folder: {folder}")

        xml_path = folder / "embFiles.xml"
        ordered_files: set[str] = set()

        if xml_path.is_file():
            tree = ET.parse(xml_path)
            root = tree.getroot()
            self.version = root.get("version", self.version)
            self.debug_have_names = (
                root.get("debugHaveNames", "false").lower() == "true"
            )

            for file_node in root.findall("File"):
                filename = file_node.get("filename") or file_node.get("name")
                internal_name = file_node.get("name") or filename
                if not filename:
                    continue
                file_path = folder / filename
                if not file_path.is_file():
                    continue
                self.files.append(EMBFile(
                    data=file_path.read_bytes(),
                    name=internal_name,
                    index=len(self.files),
                ))
                ordered_files.add(filename.lower())

        for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
            if not path.is_file():
                continue
            if path.name.lower() == "embfiles.xml":
                continue
            if path.name.lower() in ordered_files:
                continue
            self.add_file(path)

        # mimic embpack lama: file DATAxxx.dds
        for file_entry in self.files:
            if (
                len(file_entry.data) == 0
                and file_entry.name.startswith("DATA")
                and len(file_entry.name) > 4
            ):
                file_entry.name = ""

    def detect_filename_mode(self) -> bool:
        if not self.files:
            return False
        for file_entry in self.files:
            name = file_entry.name
            if "DATA" not in name or not name.lower().endswith(".dds"):
                return True
        return False

    def pack(
        self,
        folder: str | Path,
        output: str | Path,
        enable_filenames: bool | None = None,
        big_endian: bool = False,
    ) -> None:
        self.files = []
        self.add_folder(folder)
        if enable_filenames is None:
            enable_filenames = self.detect_filename_mode()
        self.save(output, enable_filenames=enable_filenames, big_endian=big_endian)

    def verify_against(self, path: str | Path) -> bool:
        try:
            reloaded = EMB().load(path)
        except Exception:
            return False
        if len(reloaded.files) != len(self.files):
            return False
        for a, b in zip(self.files, reloaded.files):
            if a.data != b.data:
                return False
        return True

    def add_entry(self, filename: str | Path) -> None:
        self.add_file(filename)

    def remove_entry(self, name: str) -> bool:
        for i, f in enumerate(self.files):
            if f.name == name:
                del self.files[i]
                for j, ff in enumerate(self.files):
                    ff.index = j
                return True
        return False

    def remove_entry_by_index(self, index: int) -> bool:
        for i, f in enumerate(self.files):
            if f.index == index:
                del self.files[i]
                for j, ff in enumerate(self.files):
                    ff.index = j
                return True
        return False

    def list_entries(self) -> None:
        for f in self.files:
            name = f.name or f"DATA{f.index:03d}.dds"
            print(f"  [{f.index:03d}] {name}  ({len(f.data)} bytes)")

    def clone(self) -> "EMB":
        new = EMB()
        new.version = self.version
        new.debug_have_names = self.debug_have_names
        new._had_names = self._had_names
        new.files = [
            EMBFile(data=f.data, name=f.name, index=f.index)
            for f in self.files
        ]
        return new