from __future__ import annotations

import struct
import pytest

from pyembpack.constants import (
    EMB_ALIGN as ALIGN,
    EMB_HEADER_SIZE as HEADER_SIZE,
    EMB_SIGNATURE as MAGIC,
)
from pyembpack.emb import EMB, EMBError, EMBFile


# builder independen, tidak lewat EMB.save()
def build_minimal_emb(
    version: bytes = b"\x01\x00\x01\x00",
    entries: list[tuple[bytes, str]] | None = None,
    with_filenames: bool = True,
) -> bytes:
    if entries is None:
        entries = [(b"AAAABBBB", "a.bin"), (b"CCCCDDDD", "b.bin")]

    buf = bytearray()
    buf += MAGIC
    buf += b"\xfe\xff"
    buf += struct.pack("<H", HEADER_SIZE)
    buf += version
    buf += struct.pack("<I", len(entries))
    buf += b"\x00" * 8
    buf += b"\x00" * 8

    data_table_address = len(buf)  # 0x20
    buf += b"\x00" * (len(entries) * 8)

    string_table_address = 0
    if with_filenames:
        string_table_address = len(buf)
        buf += b"\x00" * (len(entries) * 4)

    for i, (data, _name) in enumerate(entries):
        while len(buf) % ALIGN:
            buf.append(0)
        actual_offset = len(buf)
        rel_offset = actual_offset - i * 8 - HEADER_SIZE
        struct.pack_into(
            "<II", buf, data_table_address + i * 8, rel_offset, len(data),
        )
        buf += data

    if with_filenames:
        while len(buf) % ALIGN:
            buf.append(0)
        for i, (_data, name) in enumerate(entries):
            string_address = len(buf)
            struct.pack_into(
                "<I", buf, string_table_address + i * 4, string_address,
            )
            buf += name.encode("utf-8") + b"\x00"

    struct.pack_into("<I", buf, 0x18, data_table_address)
    struct.pack_into("<I", buf, 0x1C, string_table_address)
    return bytes(buf)


class TestLoad:
    def test_minimal_no_names(self, tmp_path):
        data = build_minimal_emb(
            version=b"\x01\x00\x01\x00",
            entries=[(b"AAAABBBB", ""), (b"CCCCDDDD", "")],
            with_filenames=False,
        )
        p = tmp_path / "x.emb"
        p.write_bytes(data)

        emb = EMB().load(p)
        assert emb.version == "1.0.1.0"
        assert len(emb.files) == 2
        assert emb.files[0].data == b"AAAABBBB"
        assert emb.files[1].data == b"CCCCDDDD"
        assert emb.debug_have_names is False
        assert emb.files[0].name == ""
        assert [f.index for f in emb.files] == [0, 1]

    def test_minimal_with_names(self, tmp_path):
        data = build_minimal_emb(
            version=b"\x01\x02\x03\x04",
            entries=[(b"hello", "first.bin"), (b"world", "second.bin")],
            with_filenames=True,
        )
        p = tmp_path / "x.emb"
        p.write_bytes(data)

        emb = EMB().load(p)
        assert emb.version == "1.2.3.4"
        assert emb.debug_have_names is True
        assert emb.files[0].name == "first.bin"
        assert emb.files[1].name == "second.bin"
        assert emb.files[0].data == b"hello"
        assert emb.files[1].data == b"world"

    def test_invalid_signature(self, tmp_path):
        p = tmp_path / "bad.emb"
        p.write_bytes(b"JUNK" + b"\x00" * 200)
        with pytest.raises(EMBError, match="signature"):
            EMB().load(p)

    def test_too_small(self, tmp_path):
        p = tmp_path / "tiny.emb"
        p.write_bytes(MAGIC + b"\x00" * 4)
        with pytest.raises(EMBError, match="too small"):
            EMB().load(p)

    def test_bad_header_size(self, tmp_path):
        data = bytearray(build_minimal_emb())
        struct.pack_into("<H", data, 0x06, 0x10)
        p = tmp_path / "x.emb"
        p.write_bytes(data)
        with pytest.raises(EMBError, match="header size"):
            EMB().load(p)

    def test_truncated_data_table(self, tmp_path):
        data = bytearray(build_minimal_emb())
        struct.pack_into("<I", data, 0x0C, 0xFFFF)
        p = tmp_path / "x.emb"
        p.write_bytes(data)
        with pytest.raises(EMBError):
            EMB().load(p)

    def test_zero_size_file(self, tmp_path):
        data = build_minimal_emb(
            entries=[(b"", ""), (b"X", "")],
            with_filenames=False,
        )
        p = tmp_path / "x.emb"
        p.write_bytes(data)
        emb = EMB().load(p)
        assert emb.files[0].data == b""
        assert emb.files[1].data == b"X"

    def test_version_zero(self, tmp_path):
        p = tmp_path / "x.emb"
        p.write_bytes(build_minimal_emb(version=b"\x00\x00\x00\x00"))
        emb = EMB().load(p)
        assert emb.version == "0.0.0.0"

    def test_version_large_bytes(self, tmp_path):
        p = tmp_path / "x.emb"
        p.write_bytes(build_minimal_emb(version=b"\x84\x92\x00\x00"))
        emb = EMB().load(p)
        assert emb.version == "132.146.0.0"

    def test_unusual_offset_formula(self, tmp_path):
        # actual_offset = 0x20 + i*8 + relative_offset
        emb = EMB()
        emb.files = [
            EMBFile(data=b"AAAA", name="", index=0),
            EMBFile(data=b"BBBB", name="", index=1),
        ]
        p = tmp_path / "x.emb"
        emb.save(p, enable_filenames=False)
        raw = p.read_bytes()

        for i in range(2):
            rel, size = struct.unpack_from("<II", raw, 0x20 + i * 8)
            actual = HEADER_SIZE + i * 8 + rel
            assert raw[actual:actual + size] in (b"AAAA", b"BBBB")


class TestSave:
    def test_roundtrip_no_filenames(self, tmp_path):
        emb = EMB()
        emb.version = "1.0.1.0"
        emb.files = [
            EMBFile(data=b"hello", name="", index=0),
            EMBFile(data=b"world", name="", index=1),
        ]
        p = tmp_path / "out.emb"
        emb.save(p, enable_filenames=False)

        loaded = EMB().load(p)
        assert loaded.version == "1.0.1.0"
        assert loaded.debug_have_names is False
        assert [f.data for f in loaded.files] == [b"hello", b"world"]

    def test_roundtrip_with_filenames(self, tmp_path):
        emb = EMB()
        emb.version = "1.0.1.0"
        emb.files = [
            EMBFile(data=b"abc", name="test.dds", index=0),
            EMBFile(data=b"defg", name="other.bin", index=1),
        ]
        p = tmp_path / "out.emb"
        emb.save(p, enable_filenames=True)

        loaded = EMB().load(p)
        assert loaded.debug_have_names is True
        assert loaded.files[0].name == "test.dds"
        assert loaded.files[1].name == "other.bin"
        assert loaded.files[0].data == b"abc"
        assert loaded.files[1].data == b"defg"

    def test_signature_and_suffix(self, tmp_path):
        emb = EMB()
        emb.files = [EMBFile(data=b"x", name="", index=0)]
        p = tmp_path / "out.emb"
        emb.save(p, enable_filenames=False)
        raw = p.read_bytes()
        assert raw[:4] == MAGIC
        assert raw[4:6] == b"\xfe\xff"

    def test_header_size_field(self, tmp_path):
        emb = EMB()
        emb.files = []
        p = tmp_path / "out.emb"
        emb.save(p, enable_filenames=False)
        raw = p.read_bytes()
        assert struct.unpack_from("<H", raw, 0x06)[0] == HEADER_SIZE

    def test_data_alignment(self, tmp_path):
        emb = EMB()
        emb.files = [
            EMBFile(data=b"a" * 10, name="", index=0),
            EMBFile(data=b"b" * 10, name="", index=1),
        ]
        p = tmp_path / "out.emb"
        emb.save(p, enable_filenames=False)
        raw = p.read_bytes()

        for i in range(2):
            rel, size = struct.unpack_from("<II", raw, 0x20 + i * 8)
            actual = HEADER_SIZE + i * 8 + rel
            assert actual % ALIGN == 0
            assert size == 10

    def test_version_short(self, tmp_path):
        emb = EMB()
        emb.version = "1.2"
        emb.files = [EMBFile(data=b"x", name="", index=0)]
        p = tmp_path / "out.emb"
        emb.save(p, enable_filenames=False)
        assert EMB().load(p).version == "1.2.0.0"

    def test_version_empty(self, tmp_path):
        emb = EMB()
        emb.version = ""
        p = tmp_path / "out.emb"
        emb.save(p, enable_filenames=False)
        assert EMB().load(p).version == "0.0.0.0"

    def test_zero_size_file_roundtrip(self, tmp_path):
        emb = EMB()
        emb.files = [
            EMBFile(data=b"", name="", index=0),
            EMBFile(data=b"x", name="", index=1),
        ]
        p = tmp_path / "out.emb"
        emb.save(p, enable_filenames=False)
        loaded = EMB().load(p)
        assert loaded.files[0].data == b""
        assert loaded.files[1].data == b"x"


class TestExtract:
    def test_creates_folder_files_and_xml(self, tmp_path):
        emb = EMB()
        emb.version = "1.0.1.0"
        emb.debug_have_names = True
        emb.files = [
            EMBFile(data=b"AAA", name="a.bin", index=0),
            EMBFile(data=b"BBB", name="b.bin", index=1),
        ]
        out = tmp_path / "out"
        emb.extract(out, progress=False)

        assert (out / "a.bin").read_bytes() == b"AAA"
        assert (out / "b.bin").read_bytes() == b"BBB"
        xml = (out / "embFiles.xml").read_text(encoding="utf-8")
        assert 'name="a.bin"' in xml
        assert 'filename="a.bin"' in xml
        assert 'version="1.0.1.0"' in xml
        assert 'debugHaveNames="true"' in xml

    def test_creates_xml_debug_have_names_false_by_default(self, tmp_path):
        emb = EMB()
        emb.version = "1.0.1.0"
        emb.files = [
            EMBFile(data=b"AAA", name="", index=0),
            EMBFile(data=b"BBB", name="", index=1),
        ]
        out = tmp_path / "out"
        emb.extract(out, progress=False)

        xml = (out / "embFiles.xml").read_text(encoding="utf-8")
        assert 'debugHaveNames="false"' in xml
        assert (out / "DATA000.dds").read_bytes() == b"AAA"
        assert (out / "DATA001.dds").read_bytes() == b"BBB"

    def test_default_names(self, tmp_path):
        emb = EMB()
        emb.files = [EMBFile(data=b"x", name="", index=i) for i in range(3)]
        out = tmp_path / "out"
        emb.extract(out, progress=False)
        assert (out / "DATA000.dds").read_bytes() == b"x"
        assert (out / "DATA001.dds").read_bytes() == b"x"
        assert (out / "DATA002.dds").read_bytes() == b"x"

    def test_default_name_formatting(self):
        emb = EMB()
        assert emb._default_name(0) == "DATA000.dds"
        assert emb._default_name(999) == "DATA999.dds"
        assert emb._default_name(1000) == "DATA1000.dds"
        assert emb._default_name(9999) == "DATA9999.dds"
        assert emb._default_name(10000) == "DATA10000.dds"

    def test_duplicate_names_get_unique_suffix(self, tmp_path):
        emb = EMB()
        emb.files = [
            EMBFile(data=b"A", name="dup.bin", index=0),
            EMBFile(data=b"B", name="dup.bin", index=1),
            EMBFile(data=b"C", name="dup.bin", index=2),
        ]
        out = tmp_path / "out"
        emb.extract(out, progress=False)
        assert (out / "dup.bin").read_bytes() == b"A"
        assert (out / "dup_1.bin").read_bytes() == b"B"
        assert (out / "dup_2.bin").read_bytes() == b"C"

    def test_dedup_case_insensitive(self, tmp_path):
        emb = EMB()
        emb.files = [
            EMBFile(data=b"A", name="File.bin", index=0),
            EMBFile(data=b"B", name="file.bin", index=1),
        ]
        out = tmp_path / "out"
        emb.extract(out, progress=False)
        assert (out / "File.bin").read_bytes() == b"A"
        assert (out / "file_1.bin").read_bytes() == b"B"

    def test_sanitizes_invalid_chars(self, tmp_path):
        emb = EMB()
        emb.files = [
            EMBFile(data=b"x", name='bad<>:"/\\|?*.bin', index=0),
        ]
        out = tmp_path / "out"
        emb.extract(out, progress=False)
        files = list(out.glob("*.bin"))
        assert len(files) == 1
        for bad in '<>:"/\\|?*':
            assert bad not in files[0].name


class TestAddFolder:
    def test_basic(self, tmp_path):
        folder = tmp_path / "pack"
        folder.mkdir()
        (folder / "one.bin").write_bytes(b"1111")
        (folder / "two.bin").write_bytes(b"2222")

        emb = EMB()
        emb.add_folder(folder)

        assert sorted(f.name for f in emb.files) == ["one.bin", "two.bin"]

    def test_ignores_embfiles_xml_as_file(self, tmp_path):
        folder = tmp_path / "pack"
        folder.mkdir()
        (folder / "one.bin").write_bytes(b"1111")
        (folder / "embFiles.xml").write_text("<EMB></EMB>")

        emb = EMB()
        emb.add_folder(folder)

        assert len(emb.files) == 1
        assert emb.files[0].name == "one.bin"

    def test_xml_ordering_and_renaming(self, tmp_path):
        folder = tmp_path / "pack"
        folder.mkdir()
        (folder / "a.bin").write_bytes(b"aaa")
        (folder / "b.bin").write_bytes(b"bbb")
        (folder / "c.bin").write_bytes(b"ccc")
        xml = """<?xml version="1.0"?>
<EMB version="2.0.0.0">
  <File name="c_renamed.bin" filename="c.bin"/>
  <File name="a_renamed.bin" filename="a.bin"/>
  <File name="b_renamed.bin" filename="b.bin"/>
</EMB>"""
        (folder / "embFiles.xml").write_text(xml)

        emb = EMB()
        emb.add_folder(folder)

        assert emb.version == "2.0.0.0"
        assert [f.name for f in emb.files] == [
            "c_renamed.bin", "a_renamed.bin", "b_renamed.bin",
        ]
        assert [f.data for f in emb.files] == [b"ccc", b"aaa", b"bbb"]

    def test_xml_with_missing_file_is_skipped(self, tmp_path):
        from pyembpack.logger import log
        log.reset()
        folder = tmp_path / "pack"
        folder.mkdir()
        (folder / "a.bin").write_bytes(b"aaa")
        xml = """<?xml version="1.0"?>
<EMB version="1.0.0.0">
  <File name="missing.bin" filename="missing.bin"/>
  <File name="a.bin" filename="a.bin"/>
</EMB>"""
        (folder / "embFiles.xml").write_text(xml)
        emb = EMB()
        emb.add_folder(folder)
        assert len(emb.files) == 1
        assert emb.files[0].name == "a.bin"
        assert log.has_warns

    def test_new_files_appended_after_xml_order(self, tmp_path):
        folder = tmp_path / "pack"
        folder.mkdir()
        (folder / "a.bin").write_bytes(b"aaa")
        (folder / "extra.bin").write_bytes(b"extra")
        xml = """<?xml version="1.0"?>
<EMB version="1.0.0.0">
  <File name="a.bin" filename="a.bin"/>
</EMB>"""
        (folder / "embFiles.xml").write_text(xml)

        emb = EMB()
        emb.add_folder(folder)
        assert [f.name for f in emb.files] == ["a.bin", "extra.bin"]

    def test_zero_size_data_file_renamed(self, tmp_path):
        folder = tmp_path / "pack"
        folder.mkdir()
        (folder / "DATA000.dds").write_bytes(b"")
        (folder / "other.bin").write_bytes(b"x")

        emb = EMB()
        emb.add_folder(folder)

        by_name = {f.name: f for f in emb.files}
        assert by_name[""].data == b""
        assert by_name["other.bin"].data == b"x"

    def test_not_a_folder(self, tmp_path):
        f = tmp_path / "x.bin"
        f.write_bytes(b"x")
        with pytest.raises(EMBError, match="Not a folder"):
            EMB().add_folder(f)


class TestAddFile:
    def test_add_file(self, tmp_path):
        f = tmp_path / "one.bin"
        f.write_bytes(b"hello")

        emb = EMB()
        emb.add_file(f)

        assert len(emb.files) == 1
        assert emb.files[0].name == "one.bin"
        assert emb.files[0].data == b"hello"
        assert emb.files[0].index == 0

    def test_missing_file(self, tmp_path):
        with pytest.raises(EMBError, match="Not a file"):
            EMB().add_file(tmp_path / "nope.bin")


class TestDetectFilenameMode:
    def test_all_data_dds_returns_false(self):
        emb = EMB()
        emb.files = [
            EMBFile(data=b"", name="DATA000.dds", index=0),
            EMBFile(data=b"", name="DATA001.dds", index=1),
        ]
        assert emb.detect_filename_mode() is False

    def test_named_files_return_true(self):
        emb = EMB()
        emb.files = [EMBFile(data=b"", name="model.emd", index=0)]
        assert emb.detect_filename_mode() is True

    def test_empty_returns_false(self):
        assert EMB().detect_filename_mode() is False

    def test_without_dds_returns_true(self):
        emb = EMB()
        emb.files = [EMBFile(data=b"", name="DATA000.bin", index=0)]
        assert emb.detect_filename_mode() is True

    def test_without_data_returns_true(self):
        emb = EMB()
        emb.files = [EMBFile(data=b"", name="thing.dds", index=0)]
        assert emb.detect_filename_mode() is True


class TestFullRoundtrip:
    def test_save_load_extract_repack(self, tmp_path):
        original = EMB()
        original.version = "1.2.3.4"
        original.files = [
            EMBFile(data=b"alpha", name="a.emd", index=0),
            EMBFile(data=b"beta!!", name="b.emb", index=1),
        ]
        src = tmp_path / "src.emb"
        original.save(src, enable_filenames=True)

        loaded = EMB().load(src)
        extract_dir = tmp_path / "extract"
        loaded.extract(extract_dir, progress=False)

        repacked = EMB()
        repacked.add_folder(extract_dir)
        repacked.save(tmp_path / "repacked.emb", enable_filenames=True)

        final = EMB().load(tmp_path / "repacked.emb")
        assert final.version == "1.2.3.4"
        assert [f.name for f in final.files] == ["a.emd", "b.emb"]
        assert [f.data for f in final.files] == [b"alpha", b"beta!!"]

class TestVerifyAgainst:
    def test_verify_ok(self, tmp_path):
        emb = EMB()
        emb.version = "1.0.1.0"
        emb.files = [
            EMBFile(data=b"abc", name="a.bin", index=0),
            EMBFile(data=b"defg", name="b.bin", index=1),
        ]
        p = tmp_path / "out.emb"
        emb.save(p, enable_filenames=True)
        assert emb.verify_against(p) is True

    def test_verify_fail_missing_file(self, tmp_path):
        emb = EMB()
        emb.files = [EMBFile(data=b"x", name="", index=0)]
        assert emb.verify_against(tmp_path / "nope.emb") is False


class TestEdit:
    def test_remove_entry_by_name(self):
        emb = EMB()
        emb.files = [
            EMBFile(data=b"1", name="a.bin", index=0),
            EMBFile(data=b"2", name="b.bin", index=1),
        ]
        assert emb.remove_entry("a.bin") is True
        assert len(emb.files) == 1
        assert emb.files[0].name == "b.bin"
        assert emb.files[0].index == 0

    def test_remove_entry_missing(self):
        emb = EMB()
        emb.files = [EMBFile(data=b"1", name="a.bin", index=0)]
        assert emb.remove_entry("nope.bin") is False

    def test_remove_entry_by_index(self):
        emb = EMB()
        emb.files = [
            EMBFile(data=b"1", name="a", index=0),
            EMBFile(data=b"2", name="b", index=1),
            EMBFile(data=b"3", name="c", index=2),
        ]
        assert emb.remove_entry_by_index(1) is True
        assert [f.name for f in emb.files] == ["a", "c"]
        assert [f.index for f in emb.files] == [0, 1]

    def test_add_entry_alias(self, tmp_path):
        f = tmp_path / "one.bin"
        f.write_bytes(b"hello")
        emb = EMB()
        emb.add_entry(f)
        assert len(emb.files) == 1
        assert emb.files[0].name == "one.bin"
        assert emb.files[0].data == b"hello"

    def test_clone_independent(self):
        emb = EMB()
        emb.version = "1.0.0.0"
        emb.files = [EMBFile(data=b"x", name="a.bin", index=0)]
        cloned = emb.clone()
        cloned.files[0].name = "b.bin"
        assert emb.files[0].name == "a.bin"


class TestSanityCaps:
    def test_file_count_too_large(self, tmp_path):
        p = tmp_path / "x.emb"
        data = bytearray(build_minimal_emb())
        struct.pack_into("<I", data, 0x0C, 999_999)
        p.write_bytes(data)
        with pytest.raises(EMBError, match="exceeds safety limit"):
            EMB().load(p)

class TestPlaceholderDetection:
    def test_metadata_dds_is_not_placeholder(self):
        emb = EMB()
        emb.files = [EMBFile(data=b"", name="METADATA.dds", index=0)]
        assert emb.detect_filename_mode() is True

    def test_somedata_prefix_is_not_placeholder(self):
        emb = EMB()
        emb.files = [EMBFile(data=b"", name="SOMEDATA000.dds", index=0)]
        assert emb.detect_filename_mode() is True

    def test_real_placeholder_is_placeholder(self):
        emb = EMB()
        for i in range(3):
            emb.files.append(EMBFile(
                data=b"", name=f"DATA{i:03d}.dds", index=i,
            ))
        assert emb.detect_filename_mode() is False

    def test_large_index_placeholder(self):
        emb = EMB()
        emb.files = [EMBFile(data=b"", name="DATA10000.dds", index=0)]
        assert emb.detect_filename_mode() is False

    def test_zero_size_database_bin_not_stripped(self, tmp_path):
        folder = tmp_path / "pack"
        folder.mkdir()
        (folder / "DATABASE.bin").write_bytes(b"")
        emb = EMB()
        emb.add_folder(folder)
        assert emb.files[0].name == "DATABASE.bin"

    def test_zero_size_data_custom_ini_not_stripped(self, tmp_path):
        folder = tmp_path / "pack"
        folder.mkdir()
        (folder / "DATA_custom.ini").write_bytes(b"")
        emb = EMB()
        emb.add_folder(folder)
        assert emb.files[0].name == "DATA_custom.ini"

    def test_missing_xml_file_emits_warning(self, tmp_path, capsys):
        from pyembpack.logger import log
        log.reset()
        folder = tmp_path / "pack"
        folder.mkdir()
        (folder / "a.bin").write_bytes(b"aaa")
        xml = """<?xml version="1.0"?>
<EMB version="1.0.0.0">
  <File name="gone.bin" filename="gone.bin"/>
  <File name="a.bin" filename="a.bin"/>
</EMB>"""
        (folder / "embFiles.xml").write_text(xml)
        emb = EMB()
        emb.add_folder(folder)
        captured = capsys.readouterr()
        assert "Missing file" in captured.out
        assert "gone.bin" in captured.out