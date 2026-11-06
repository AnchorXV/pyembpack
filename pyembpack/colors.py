import sys


def _enable_win_ansi() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # -11 = STD_OUTPUT_HANDLE, -12 = STD_ERROR_HANDLE
        for handle_id in (-11, -12):
            handle = kernel32.GetStdHandle(handle_id)
            if handle and handle != -1:
                mode = ctypes.c_ulong()
                if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                    kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


_enable_win_ansi()


def _color(text: str, code: str) -> str:
    try:
        if sys.stdout.isatty():
            return f"{code}{text}\033[0m"
    except Exception:
        pass
    return text


def _color_err(text: str, code: str) -> str:
    try:
        if sys.stderr.isatty():
            return f"{code}{text}\033[0m"
    except Exception:
        pass
    return text


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    BLUE = "\033[94m"
    GREY = "\033[90m"
    WHITE = "\033[97m"

    @staticmethod
    def error(msg: str) -> str:
        return _color_err(f"[ERROR] {msg}", C.RED + C.BOLD)

    @staticmethod
    def warn(msg: str) -> str:
        return _color(f"[WARN]  {msg}", C.YELLOW + C.BOLD)

    @staticmethod
    def ok(msg: str) -> str:
        return _color(f"[OK]    {msg}", C.GREEN + C.BOLD)

    @staticmethod
    def info(msg: str) -> str:
        return _color(f"[INFO]  {msg}", C.CYAN)

    @staticmethod
    def detail(msg: str) -> str:
        return _color(f"        {msg}", C.GREY)