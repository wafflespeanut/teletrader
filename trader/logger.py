import logging
import termcolor


class ColoredAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        kv = {}
        color = kwargs.pop("color", None)
        if color:
            kv["color"] = color
        on_color = kwargs.pop("on", None)
        if on_color:
            kv["on_color"] = "on_" + on_color
        if kv:
            msg = termcolor.colored(msg, **kv)
        return msg, kwargs


class ColoredFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: (["grey"], {}),
        logging.INFO: ([], {}),
        logging.WARNING: (["yellow"], {}),
        logging.ERROR: (["red"], {}),
        logging.CRITICAL: (["red"], {"attrs": ["bold"]})
    }

    def format(self, record: logging.LogRecord):
        args, kwargs = self.COLORS[record.levelno]
        fmt = termcolor.colored("%(levelname)s: %(message)s", *args, **kwargs)
        return logging.Formatter(fmt).format(record)


ROOT = logging.getLogger()
ROOT.setLevel(logging.INFO)
hdr = logging.StreamHandler()
hdr.setFormatter(ColoredFormatter())
ROOT.addHandler(hdr)

DEFAULT_LOGGER = ColoredAdapter(ROOT, {})
