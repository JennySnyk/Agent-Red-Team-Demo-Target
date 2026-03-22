import logging

from flask import g


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not g:
            record.request_id = "N/A"
            return True
        record.request_id = g.get("request_id", "ERROR NOT FOUND")
        return True


def get_logger(module_name: str) -> logging.Logger:
    logger = logging.getLogger(module_name)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(levelname)s:%(name)s: ID: %(request_id)s: %(message)s",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.addFilter(RequestIdFilter())
    logger.propagate = False
    return logger
