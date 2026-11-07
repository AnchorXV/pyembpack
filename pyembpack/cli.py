import argparse
import glob
import sys
from pathlib import Path
from typing import Optional

from .colors import C
from .logger import log
from .emb import EMB
from .pathutils import backup_file


def _version() -> str:
    try:
        from . import __version__
        return __version__
    except Exception:
        return "unknown"


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False) or "__compiled__" in globals()


def _stdin_is_tty() -> bool:
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def _pause(args=None, force: bool = False) -> None:
    should = False
    if force:
        should = True
    elif args is not None:
        if getattr(args, "wait", False):
            should = True
        elif getattr(args, "no_wait", False):
            should = False
        elif _is_frozen():
            should = True
        else:
            should = log.has_errors

    if not should:
        return
    if not _stdin_is_tty():
        return
    try:
        input("\nPress Enter to continue...")
    except EOFError:
        pass


def _validate_flags(args) -> Optional[str]:
    if args.add and args.remove:
        return "--add and --remove cannot be used together"
    if (args.add or args.remove) and (args.extract or args.repack or args.list):
        return "--add/--remove cannot be combined with -x, -r, or -l"
    return None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pyembpack",
        description=(
            f"{C.BOLD}{C.CYAN}pyembpack{C.RESET} - "
            "EMB Archive Tool for Dragon Ball Xenoverse\n"
            "Extract, repack, inspect, and modify .emb archives.\n\n"
            "Auto-detects mode: .emb file -> extract, folder -> repack.\n"
            "Supports glob patterns for batch processing."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  pyembpack character.emb                # extract\n"
            "  pyembpack character/                    # repack\n"
            "  pyembpack -l character.emb              # list contents\n"
            "  pyembpack -x character.emb -o out/      # extract to custom dir\n"
            "  pyembpack --verify character.emb        # verify integrity\n"
            "  pyembpack --add new.dds character.emb   # add file\n"
            "  pyembpack --remove old.dds character.emb # remove file\n"
            "  pyembpack --check character/            # repack + verify\n"
            "  pyembpack *.emb                         # batch extract\n"
        ),
    )
    p.add_argument(
        "inputs", nargs="+", metavar="FILE|FOLDER",
        help="Input .emb file(s), folder(s), or glob pattern(s).",
    )

    mode = p.add_mutually_exclusive_group()
    mode.add_argument("-x", "--extract", action="store_true",
                      help="Force extract mode.")
    mode.add_argument("-r", "--repack", action="store_true",
                      help="Force repack mode.")
    mode.add_argument("-l", "--list", action="store_true",
                      help="List contents of .emb file(s).")
    mode.add_argument("--verify", action="store_true",
                      help="Verify .emb file integrity.")

    p.add_argument("--add", metavar="FILE", default=None,
                   help="Add FILE to the .emb archive.")
    p.add_argument("--remove", metavar="NAME", default=None,
                   help="Remove entry by name from the archive.")
    p.add_argument("-o", "--output", metavar="PATH", default=None,
                   help="Output directory (extract) or filename (repack).")
    p.add_argument("--check", action="store_true",
                   help="After pack/edit, reload and verify integrity.")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview actions without writing files.")
    p.add_argument("--no-filenames", action="store_true",
                   help="Pack without filename table.")
    p.add_argument("-q", "--quiet", "--silent", action="store_true",
                   dest="silent",
                   help="Suppress all output except errors.")
    p.add_argument("--verbose", action="store_true",
                   help="Show per-file details.")
    p.add_argument("--wait", action="store_true",
                   help="Pause and wait for Enter at the end.")
    p.add_argument("--no-wait", action="store_true",
                   help="Never pause at the end.")
    p.add_argument("--version", action="version",
                   version=f"pyembpack {_version()}")
    return p


def _detail_entries(emb: EMB) -> None:
    for f in emb.files:
        name = f.name or f"DATA{f.index:03d}.dds"
        log.detail(f"[{f.index:03d}] {name}  ({len(f.data)} bytes)")


def process_extract(emb_path: Path, out_dir: Optional[Path], dry_run: bool) -> bool:
    try:
        emb = EMB().load(emb_path)
    except Exception as e:
        log.error(f"Failed to load '{emb_path.name}': {e}")
        return False

    dest = out_dir if out_dir else emb_path.parent / emb_path.stem

    if dry_run:
        log.dry(f"Would extract {len(emb.files)} files to: {dest}")
        _detail_entries(emb)
        return True

    emb.extract(dest, progress=not log.silent)
    _detail_entries(emb)
    log.ok(f"Extracted {len(emb.files)} files to: {dest}")
    return True


def process_repack(folder: Path, out_path: Optional[Path], dry_run: bool,
                   check: bool, no_filenames: bool) -> bool:
    emb = EMB()
    try:
        emb.add_folder(folder, progress=not log.silent)
    except Exception as e:
        log.error(f"Failed to read folder '{folder}': {e}")
        return False

    dest = out_path if out_path else folder.parent / (folder.name + ".emb")
    if dest.suffix.lower() != ".emb":
        dest = dest.with_suffix(".emb")

    enable_filenames = False if no_filenames else emb.detect_filename_mode()

    if dry_run:
        log.dry(f"Would pack {len(emb.files)} files into: {dest}")
        log.dry(f"  filenames={'yes' if enable_filenames else 'no'}")
        _detail_entries(emb)
        return True

    emb.save(dest, enable_filenames=enable_filenames)
    _detail_entries(emb)
    log.ok(f"Packed {len(emb.files)} files into: {dest}")

    if check:
        log.info("Verifying…")
        if emb.verify_against(dest):
            log.ok("Verification passed.")
        else:
            log.error("Verification FAILED.")
            return False
    return True


def process_list(emb_path: Path) -> bool:
    try:
        emb = EMB().load(emb_path)
    except Exception as e:
        log.error(f"Failed to load '{emb_path.name}': {e}")
        return False

    print(
        f"\n{emb_path.name}  "
        f"[version={emb.version}, files={len(emb.files)}, "
        f"filenames={'yes' if emb.debug_have_names else 'no'}]"
    )
    emb.list_entries()
    return True


def process_verify(emb_path: Path) -> bool:
    try:
        emb = EMB().load(emb_path)
    except Exception as e:
        log.error(f"Failed to load '{emb_path.name}': {e}")
        return False

    total = sum(len(f.data) for f in emb.files)
    log.ok(
        f"{emb_path.name}: {len(emb.files)} files, {total} bytes, "
        f"version={emb.version}, "
        f"filenames={'yes' if emb.debug_have_names else 'no'}"
    )
    return True


def process_add(emb_path: Path, add_file: Path, out_path: Optional[Path],
                dry_run: bool, check: bool) -> bool:
    try:
        emb = EMB().load(emb_path)
    except Exception as e:
        log.error(f"Failed to load '{emb_path.name}': {e}")
        return False

    try:
        emb.add_entry(add_file)
    except Exception as e:
        log.error(str(e))
        return False

    log.info(f"Added: {add_file.name}")
    dest = out_path or emb_path
    same = dest.resolve() == emb_path.resolve()

    if dry_run:
        log.dry(f"Would save to: {dest}")
        if same:
            log.dry(f"Would backup: {dest.name} -> {dest.name}.bak")
        return True

    if same:
        bak = backup_file(dest)
        log.info(f"Backup created: {bak.name}")

    emb.save(dest, enable_filenames=emb._had_names)
    log.ok(f"Saved: {dest}")

    if check and not emb.verify_against(dest):
        log.error("Verification FAILED.")
        return False
    return True


def process_remove(emb_path: Path, remove_name: str, out_path: Optional[Path],
                   dry_run: bool, check: bool) -> bool:
    try:
        emb = EMB().load(emb_path)
    except Exception as e:
        log.error(f"Failed to load '{emb_path.name}': {e}")
        return False

    if not emb.remove_entry(remove_name):
        log.error(f"Entry not found: '{remove_name}'")
        return False

    log.info(f"Removed: {remove_name}")
    dest = out_path or emb_path
    same = dest.resolve() == emb_path.resolve()

    if dry_run:
        log.dry(f"Would save to: {dest}")
        if same:
            log.dry(f"Would backup: {dest.name} -> {dest.name}.bak")
        return True

    if same:
        bak = backup_file(dest)
        log.info(f"Backup created: {bak.name}")

    emb.save(dest, enable_filenames=emb._had_names)
    log.ok(f"Saved: {dest}")

    if check and not emb.verify_against(dest):
        log.error("Verification FAILED.")
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    log.reset()
    parser = build_parser()

    if not argv:
        parser.print_help()
        if _is_frozen():
            _pause(force=True)
        return 0

    args = parser.parse_args(argv)
    log.silent = args.silent
    log.verbose = args.verbose

    validation_error = _validate_flags(args)
    if validation_error:
        log.error(validation_error)
        _pause(args)
        return 1

    if args.dry_run:
        log.info("DRY RUN MODE - no files will be written.")

    resolved: list[Path] = []
    for pattern in args.inputs:
        matches = [Path(p) for p in glob.glob(pattern, recursive=True)]
        if matches:
            resolved.extend(matches)
        else:
            p = Path(pattern)
            if p.exists():
                resolved.append(p)
            else:
                log.warn(f"No match for input: '{pattern}'")

    if not resolved:
        log.error("No valid input files or folders found.")
        _pause(args)
        return 1

    if args.output and len(resolved) > 1 and not (args.verify or args.list):
        log.error("--output can only be used with a single input")
        _pause(args)
        return 1

    out_path = Path(args.output) if args.output else None
    add_file = Path(args.add) if args.add else None

    success = 0
    fail = 0

    for inp in resolved:
        is_emb = inp.is_file() and inp.suffix.lower() == ".emb"
        is_folder = inp.is_dir()

        if args.verify:
            mode = "verify"
        elif args.list:
            mode = "list"
        elif args.add or args.remove:
            mode = "edit"
        elif args.extract:
            mode = "extract"
        elif args.repack:
            mode = "repack"
        elif is_emb:
            mode = "extract"
        elif is_folder:
            mode = "repack"
        else:
            log.error(f"Cannot determine mode for '{inp}'.")
            fail += 1
            continue

        ok = False

        if mode == "verify":
            if not is_emb:
                log.error(f"--verify requires a .emb file: '{inp}'")
                fail += 1
                continue
            ok = process_verify(inp)

        elif mode == "list":
            if not is_emb:
                log.error(f"--list requires a .emb file: '{inp}'")
                fail += 1
                continue
            ok = process_list(inp)

        elif mode == "extract":
            if not is_emb:
                log.error(f"Extract mode requires a .emb file: '{inp}'")
                fail += 1
                continue
            dest = out_path if (out_path and len(resolved) == 1) else None
            ok = process_extract(inp, dest, args.dry_run)

        elif mode == "repack":
            if not is_folder:
                log.error(f"Repack mode requires a folder: '{inp}'")
                fail += 1
                continue
            dest = out_path if (out_path and len(resolved) == 1) else None
            ok = process_repack(inp, dest, args.dry_run, args.check,
                                args.no_filenames)

        elif mode == "edit":
            if not is_emb:
                log.error(f"--add/--remove requires a .emb file: '{inp}'")
                fail += 1
                continue
            if args.add:
                ok = process_add(inp, add_file, out_path, args.dry_run,
                                 args.check)
            elif args.remove:
                ok = process_remove(inp, args.remove, out_path, args.dry_run,
                                    args.check)

        if ok:
            success += 1
        else:
            fail += 1

    total = success + fail
    if total > 1:
        log.info(f"Done: {success} ok, {fail} failed ({total} total)")
    elif not log.has_errors and not log.has_warns:
        log.ok("Finished.")

    _pause(args)

    if fail > 0:
        return 1
    if log.has_warns:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())