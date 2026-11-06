from __future__ import annotations

from pathlib import Path

from pyembpack import cli
from pyembpack.emb import EMB, EMBFile


def _make_sample_emb(path: Path, with_names: bool = True) -> None:
    emb = EMB()
    emb.version = "1.0.1.0"
    emb.files = [
        EMBFile(data=b"alpha", name="a.emd" if with_names else "", index=0),
        EMBFile(data=b"beta", name="b.emb" if with_names else "", index=1),
    ]
    emb.save(path, enable_filenames=with_names)


class TestNoArgs:
    def test_no_args_prints_help(self, capsys):
        rc = cli.main([])
        assert rc == 0
        out = capsys.readouterr().out
        assert "pyembpack" in out
        assert "extract" in out.lower()


class TestExtractCli:
    def test_extract_single_with_output(self, tmp_path):
        emb_path = tmp_path / "sample.emb"
        _make_sample_emb(emb_path, with_names=True)
        out_dir = tmp_path / "out"

        rc = cli.main([
            str(emb_path), "--output", str(out_dir), "--quiet", "--no-wait",
        ])
        assert rc == 0
        assert (out_dir / "a.emd").read_bytes() == b"alpha"
        assert (out_dir / "b.emb").read_bytes() == b"beta"
        assert (out_dir / "embFiles.xml").exists()

    def test_extract_default_output_folder(self, tmp_path):
        emb_path = tmp_path / "sample.emb"
        _make_sample_emb(emb_path, with_names=True)

        rc = cli.main([str(emb_path), "--quiet", "--no-wait"])
        assert rc == 0
        assert (tmp_path / "sample" / "a.emd").read_bytes() == b"alpha"

    def test_extract_multiple_emb_files(self, tmp_path):
        _make_sample_emb(tmp_path / "x.emb", with_names=True)
        _make_sample_emb(tmp_path / "y.emb", with_names=True)

        rc = cli.main([
            str(tmp_path / "x.emb"),
            str(tmp_path / "y.emb"),
            "--quiet", "--no-wait",
        ])
        assert rc == 0
        assert (tmp_path / "x" / "a.emd").exists()
        assert (tmp_path / "y" / "a.emd").exists()

    def test_extract_invalid_emb_returns_1(self, tmp_path, capsys):
        bad = tmp_path / "bad.emb"
        bad.write_bytes(b"NOTEMB" + b"\x00" * 100)
        rc = cli.main([str(bad), "--quiet", "--no-wait"])
        assert rc == 1
        assert "ERROR" in capsys.readouterr().err


class TestVerify:
    def test_verify_ok(self, tmp_path, capsys):
        emb_path = tmp_path / "sample.emb"
        _make_sample_emb(emb_path)

        rc = cli.main(["--verify", str(emb_path), "--no-wait"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "[OK]" in out
        assert "2 files" in out
        assert "version=1.0.1.0" in out

    def test_verify_not_emb_extension(self, tmp_path, capsys):
        f = tmp_path / "not_emb.bin"
        f.write_bytes(b"x")
        rc = cli.main(["--verify", str(f), "--no-wait"])
        assert rc == 1
        assert "ERROR" in capsys.readouterr().err

    def test_verify_corrupt_file(self, tmp_path, capsys):
        bad = tmp_path / "bad.emb"
        bad.write_bytes(b"JUNK" + b"\x00" * 100)
        rc = cli.main(["--verify", str(bad), "--no-wait"])
        assert rc == 1

    def test_verify_multiple_files(self, tmp_path, capsys):
        _make_sample_emb(tmp_path / "a.emb")
        _make_sample_emb(tmp_path / "b.emb")

        rc = cli.main([
            "--verify",
            str(tmp_path / "a.emb"),
            str(tmp_path / "b.emb"),
            "--no-wait",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert out.count("[OK]") == 2

    def test_verify_with_output_and_multiple_does_not_error(self, tmp_path):
        _make_sample_emb(tmp_path / "a.emb")
        _make_sample_emb(tmp_path / "b.emb")

        rc = cli.main([
            "--verify",
            str(tmp_path / "a.emb"),
            str(tmp_path / "b.emb"),
            "--output", str(tmp_path / "unused"),
            "--no-wait",
        ])
        assert rc == 0


class TestPackCli:
    def test_pack_folder_with_output(self, tmp_path):
        folder = tmp_path / "mypack"
        folder.mkdir()
        (folder / "a.emd").write_bytes(b"alpha")
        (folder / "b.emb").write_bytes(b"beta")
        output = tmp_path / "out.emb"

        rc = cli.main([
            str(folder), "--output", str(output), "--quiet", "--no-wait",
        ])
        assert rc == 0
        assert output.exists()
        loaded = EMB().load(output)
        assert len(loaded.files) == 2

    def test_pack_folder_default_output(self, tmp_path):
        folder = tmp_path / "mypack"
        folder.mkdir()
        (folder / "a.emd").write_bytes(b"alpha")

        rc = cli.main([str(folder), "--quiet", "--no-wait"])
        assert rc == 0
        assert (tmp_path / "mypack.emb").exists()
        assert EMB().load(tmp_path / "mypack.emb").version

    def test_pack_no_filenames(self, tmp_path):
        folder = tmp_path / "mypack"
        folder.mkdir()
        (folder / "a.emd").write_bytes(b"alpha")
        output = tmp_path / "out.emb"

        rc = cli.main([
            str(folder),
            "--output", str(output),
            "--no-filenames",
            "--quiet", "--no-wait",
        ])
        assert rc == 0
        assert EMB().load(output).debug_have_names is False

    def test_pack_preserves_xml_order_and_version(self, tmp_path):
        folder = tmp_path / "mypack"
        folder.mkdir()
        (folder / "a.bin").write_bytes(b"aaa")
        (folder / "b.bin").write_bytes(b"bbb")
        xml = """<?xml version="1.0"?>
<EMB version="1.5.0.0">
  <File name="b.bin" filename="b.bin"/>
  <File name="a.bin" filename="a.bin"/>
</EMB>"""
        (folder / "embFiles.xml").write_text(xml)
        output = tmp_path / "out.emb"

        rc = cli.main([
            str(folder), "--output", str(output), "--quiet", "--no-wait",
        ])
        assert rc == 0
        loaded = EMB().load(output)
        assert loaded.version == "1.5.0.0"
        assert [f.name for f in loaded.files] == ["b.bin", "a.bin"]


class TestErrors:
    def test_output_with_multiple_inputs_rejected(self, tmp_path, capsys):
        _make_sample_emb(tmp_path / "a.emb")
        _make_sample_emb(tmp_path / "b.emb")

        rc = cli.main([
            str(tmp_path / "a.emb"),
            str(tmp_path / "b.emb"),
            "--output", str(tmp_path / "out"),
            "--no-wait",
        ])
        assert rc == 1
        assert "ERROR" in capsys.readouterr().err

    def test_unsupported_path(self, tmp_path, capsys):
        f = tmp_path / "file.txt"
        f.write_text("hi")
        rc = cli.main([str(f), "--no-wait"])
        assert rc == 1
        assert "ERROR" in capsys.readouterr().err

    def test_missing_file(self, tmp_path, capsys):
        rc = cli.main([str(tmp_path / "nope.emb"), "--no-wait"])
        assert rc == 1
        assert "ERROR" in capsys.readouterr().err

    def test_multiple_paths_continue_after_failure(self, tmp_path):
        bad = tmp_path / "bad.emb"
        bad.write_bytes(b"JUNK" + b"\x00" * 100)
        good = tmp_path / "good.emb"
        _make_sample_emb(good, with_names=True)

        rc = cli.main([str(bad), str(good), "--quiet", "--no-wait"])
        assert rc == 1
        assert (tmp_path / "good" / "a.emd").exists()