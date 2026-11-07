import sys

from .colors import C


class Logger:
    def __init__(self) -> None:
        self.silent = False
        self.verbose = False
        self._errors = 0
        self._warns = 0

    def reset(self) -> None:
        self.silent = False
        self.verbose = False
        self._errors = 0
        self._warns = 0

    def error(self, msg: str) -> None:
        self._errors += 1
        print(C.error(msg), file=sys.stderr)

    def warn(self, msg: str) -> None:
        self._warns += 1
        if not self.silent:
            print(C.warn(msg))

    def ok(self, msg: str) -> None:
        if not self.silent:
            print(C.ok(msg))

    def info(self, msg: str) -> None:
        if not self.silent:
            print(C.info(msg))

    def detail(self, msg: str) -> None:
        if self.verbose and not self.silent:
            print(C.detail(msg))

    def dry(self, msg: str) -> None:
        if not self.silent:
            print(_color_dry(f"[DRY]   {msg}"))

    @property
    def has_errors(self) -> bool:
        return self._errors > 0

    @property
    def has_warns(self) -> bool:
        return self._warns > 0


def _color_dry(text: str) -> str:
    from .colors import _color
    return _color(text, "\033[94m\033[1m")


log = Logger()