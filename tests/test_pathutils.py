from pyembpack.pathutils import backup_file, sanitize_filename


class TestSanitize:
    def test_strips_path_traversal(self):
        assert sanitize_filename("../../etc/passwd") == "passwd"

    def test_strips_windows_separator(self):
        assert sanitize_filename("a\\b\\c.dds") == "c.dds"

    def test_replaces_invalid_chars(self):
        out = sanitize_filename('bad<>:"/\\|?*.bin')
        for ch in '<>:"/\\|?*':
            assert ch not in out

    def test_strips_leading_dots(self):
        assert sanitize_filename("...hidden.txt") == "hidden.txt"

    def test_empty_fallback(self):
        assert sanitize_filename("") == "_unnamed"


class TestBackup:
    def test_first_backup(self, tmp_path):
        f = tmp_path / "a.emb"
        f.write_bytes(b"v1")
        bak = backup_file(f)
        assert bak.name == "a.emb.bak"
        assert bak.read_bytes() == b"v1"

    def test_rotation(self, tmp_path):
        f = tmp_path / "a.emb"
        f.write_bytes(b"v1")
        backup_file(f)
        f.write_bytes(b"v2")
        backup_file(f)
        f.write_bytes(b"v3")
        backup_file(f)

        assert (tmp_path / "a.emb.bak").read_bytes() == b"v3"
        assert (tmp_path / "a.emb.bak.2").read_bytes() == b"v2"
        assert (tmp_path / "a.emb.bak.3").read_bytes() == b"v1"

    def test_dry_run_no_write(self, tmp_path):
        f = tmp_path / "a.emb"
        f.write_bytes(b"v1")
        backup_file(f, dry_run=True)
        assert not (tmp_path / "a.emb.bak").exists()

    def test_no_backup_when_missing(self, tmp_path):
        f = tmp_path / "nope.emb"
        assert backup_file(f) == f