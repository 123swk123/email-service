# SPDX-FileCopyrightText: 2024-present SwK <swk@swkemb.com>
#
# SPDX-License-Identifier: MIT

import queue
from typing import Optional
import picologging as logging
from picologging.handlers import QueueHandler, QueueListener
# or
# import logging
# from logging.handlers import QueueHandler, QueueListener

ILogger = logging.Logger
IQueueListener = QueueListener

class ColorFormatter(logging.Formatter):
    def format(self, record:logging.LogRecord) -> str:
        color_map = {
            'DEBUG': '\x1b[37m',
            'INFO': '\x1b[92m',
            'WARN': '\x1b[93m',
            'WARNING': '\x1b[93m',
            'ERROR': '\x1b[91m',
            # 'CRITICAL': '\x1b[31m\x1b[1m\x1b[107m', #clr.Fore.RED+clr.Style.BRIGHT+clr.Back.LIGHTWHITE_EX
            'CRITICAL': '\x1b[1m\x1b[41m\x1b[97m', #clr.Style.BRIGHT+clr.Back.RED+clr.Fore.LIGHTWHITE_EX
        }
        # record.levelname = color_map.get(record.levelname, '\x1b[0m') + record.levelname + '\x1b[0m'
        return color_map.get(record.levelname, '\x1b[0m') + super().format(record) + '\x1b[0m'

def utils_get_logger(name:str, que:Optional[queue.Queue]=None, level:int=logging.WARNING, fmt:str='%(levelname)s:%(process)d => %(message)s') -> ILogger:
    logger = logging.getLogger(name)

    # looks like this logger is already configured
    if len(logger.handlers) > 0:
        # print('Logger already configured:', name, logger.handlers)
        return logger

    if que := que:
        _h = QueueHandler(que)
    else:
        _h = logging.StreamHandler()
    # https://docs.python.org/3.13/library/logging.html#logrecord-attributes
    _fmt = ColorFormatter(fmt)
    _h.setFormatter(_fmt)
    logger.addHandler(_h)
    logger.setLevel(level)
    return logger
