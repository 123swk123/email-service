# SPDX-FileCopyrightText: 2024-present SwK <swk@swkemb.com>
#
# SPDX-License-Identifier: MIT

import asyncio
import multiprocessing
import queue
import random
import signal
import smtplib
import sys
from email.message import EmailMessage
from typing import Any, Callable, ClassVar, Dict, NoReturn, Optional

from confz import BaseConfig, EnvSource
from nicegui import run
from pydantic import ValidationError
from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from .utils import IQueueListener, logging, utils_get_logger

log_listener: IQueueListener
mail_process_tasks: list[asyncio.Task[None]] = []

class ConfigSMTP(BaseConfig):
    host: str
    port: int = 25
    starttls: bool = False
    from_email: str
    username: str
    password: str
    keep_alive_interval: int = 120
    debug: bool = False

class SrvcEmail():

    self_objects:ClassVar[dict[int, 'SrvcEmail']] = {}
    logger: logging.Logger
    _m_memdb_host: str
    _m_config: ConfigSMTP
    m_smtp: smtplib.SMTP
    m_subscription: PubSub
    m_channel_map: Dict[str, Callable[[bytes | bytearray], EmailMessage]]
    m_task_keep_alive: asyncio.Task[NoReturn]

    __slots__ = ['_m_memdb_host', '_m_config', 'm_smtp', 'm_subscription', 'm_channel_map', 'm_task_keep_alive']

    def __new__(cls, *args, **kwargs):
        rtn = super().__new__(cls)
        cls.self_objects[id(rtn)] = rtn
        return rtn

    def __del__(self):
        del self.self_objects[id(self)]

    def __init__(self, memdb_host: str) -> None:
        self._m_memdb_host = memdb_host
        self.m_channel_map = {}

    def __repr__(self) -> str:
        rtn = f'0x{id(self):x} ->\n'
        if hasattr(self, '_m_config'): rtn += f'\tSMTP Config: {self._m_config}\n'
        if hasattr(self, 'm_channel_map'): rtn += f'\t{self.m_channel_map}\n'
        if hasattr(self, 'm_subscription'): rtn += f'\t{self.m_subscription}'
        return rtn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        pass

    def _message_handler_(self, message: Dict[str, Any]):
        async def _republish(wait_time:float):
            await asyncio.sleep(wait_time)
            await Redis(host=self._m_memdb_host).publish(message['channel'], message['data'])

        def republish(wait_time:float = -1):
            wait_time = random.randrange(5, 30, 5) if wait_time < 0 else wait_time
            asyncio.run_coroutine_threadsafe(_republish(wait_time), asyncio.get_event_loop())

        # self.logger.debug('from _message_handler_: %s', message)
        email_msg:Optional[EmailMessage] = None
        try:
            registered_handler = self.m_channel_map[message['channel'].decode()]
            if registered_handler:
                email_msg = registered_handler(message['data'])
                self.m_smtp.send_message(email_msg, mail_options=['SMTPUTF8'])
            else:
                self.logger.warning('No eMail handler found for channel: %s', message['channel'])
        except smtplib.SMTPSenderRefused as excp:
            if excp.smtp_code >= 500 and excp.smtp_code <= 599:
                if self._m_config.starttls: self.m_smtp.starttls()
                rslt = self.m_smtp.login(self._m_config.username, self._m_config.password)
                self.logger.debug('Re-trying authentication: %s', rslt)
                republish(0)
            else:
                self.logger.warning('SMTP Server Refused with (%d) %s by %s', *excp.args)
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError):
            self.logger.error('SMTP rejected due to invalid recipient(s) or Data error, we will not retry this email.')
            if email_msg: self.logger.error('Subject: %s, To: %s', email_msg.get('Subject'), email_msg.get('To'))
        except smtplib.SMTPServerDisconnected:
            self.logger.warning('SMTPServerDisconnected, reconnecting')
            self._reconnect_smtp()
            republish()
        except Exception as excp:
            self.logger.exception(repr(excp))

    def register_email_channel(self, ch_name:str, ch_mssg_conv: Callable[[bytes | bytearray], EmailMessage]):
        self.m_channel_map[ch_name] = ch_mssg_conv

    async def _keep_alive_smtp(self, interval:int = 60):
        while True:
            await asyncio.sleep(interval)
            try:
                self.m_smtp.noop()
            except smtplib.SMTPServerDisconnected:
                self.logger.debug('SMTPServerDisconnected, reconnecting')
                self._reconnect_smtp()
            except Exception as excp:
                self.logger.exception(repr(excp))

    def _terminate_smtp(self):
        try:
            self.m_smtp.quit()
        except smtplib.SMTPServerDisconnected:
            pass

    def _reconnect_smtp(self):
        try:
            # try:
            #     self._terminate_smtp()
            # except Exception:
            #     pass
            rslt = self.m_smtp.connect(self._m_config.host, self._m_config.port)
            self.logger.debug('connect: %s', rslt)
            # if self._m_config.starttls: self.m_smtp.starttls()
            rslt = self.m_smtp.login(self._m_config.username, self._m_config.password)
            self.logger.debug('authentication: %s', rslt)
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, smtplib.SMTPResponseException) as excp:
            self.logger.warning('SMTPException: %r', excp)
        except Exception as excp:
            self.logger.exception(repr(excp))

    async def _do_work(self):
        """
        This method performs the main work of watching for incoming mail request and sends it out via SMTP.
        - set up a global signal handlers for CTRL+C(SIGINT) & Process Kill(SIGTERM) so that we can terminate our process
        - subscribes to list of channel as requested by user via `register_email_channel`
        - listens for mail request messages on the channels endlessly.
            - upon receiving a message, call the `_message_handler_`, process it using the user supplied message converter and send out the mail.
            - if parent process request us stop via SIGINT or SIGTERM, we raise `asyncio.CancelledError` and wait for closure.
        - Finally, the subscription is closed.

        Raises: None
        """
        def raise_cancel(sig, frame):
            raise asyncio.CancelledError()

        signal.signal(signal.SIGINT, raise_cancel)
        signal.signal(signal.SIGTERM, raise_cancel)

        # prepare the channel, allows us to listen for the messages under this subscription
        # WRKARND: we wait for each subscription to complete before moving to the next one.
        for ch_name in self.m_channel_map.keys():
            await self.m_subscription.subscribe(ch_name, **{ch_name: self._message_handler_})

        # BUG: gathering coroutines in a list and then awaiting them is not working as expected.
        # async with asyncio.TaskGroup() as tg:
        #     for ch_name in self.m_channel_map.keys():
        #         tg.create_task(self.m_subscription.subscribe(ch_name, **{ch_name: self._message_handler_}))

        # rslt = map(lambda ch_name: self.m_subscription.subscribe(ch_name, **{ch_name: self._message_handler_}), self.m_channel_map.keys())
        # rslt = await asyncio.gather(*rslt)
        # self.logger.debug('subscribed:', rslt)

        # now listen for the messages endlessly and do SMTP connection maintenance
        self.m_task_keep_alive = asyncio.create_task(self._keep_alive_smtp(self._m_config.keep_alive_interval))
        try:
            await self.m_subscription.run()
        except asyncio.CancelledError:
            self.logger.debug('closing subscription')
            await self.do_force_closure()
        except Exception as excp:
            self.logger.exception(repr(excp))
        finally:
            self.logger.debug('_do_work, finally')

    async def do_force_closure(self):
        if hasattr(self, 'm_task_keep_alive.cancel'):
            self.m_task_keep_alive.cancel()
        if hasattr(self, 'm_subscription.aclose'):
            await self.m_subscription.aclose()

    def entry(self, que: queue.Queue, log_level:int = logging.DEBUG):
        SrvcEmail.logger = utils_get_logger(self.__class__.__name__, que, log_level, '%(levelname)s:%(name)s:%(process)d => %(message)s')

        try:
            self._m_config = ConfigSMTP(config_sources=EnvSource(allow_all=True, prefix='SMTP_'))
            self.m_subscription = Redis(host=self._m_memdb_host).pubsub()
            self.m_smtp = smtplib.SMTP(self._m_config.host, self._m_config.port, timeout=30)
            self.m_smtp.set_debuglevel(1 if self._m_config.debug else 0)
            self.logger.debug('self %r', self)
            if self._m_config.starttls:
                self.m_smtp.starttls()
            rslt = self.m_smtp.login(self._m_config.username, self._m_config.password)
            self.logger.info('login: %s', rslt)

            asyncio.run(self._do_work())
        except ValidationError as excp:
            # catch missing or invalid environment variables
            for error in excp.errors():
                if error["type"] == 'missing':
                    self.logger.critical('%s environment variable not found.', str(error["loc"][0]).upper())
                else:
                    self.logger.critical('you have set %s="%s" but %s', str(error["loc"][0]).upper(), error["input"], error["msg"])
            self.logger.critical('eMail service is not available! fix the environment variables and restart the service.')
        except smtplib.SMTPAuthenticationError as excp:
            self.logger.info('SMTP Error Details: %r', excp)
            self.logger.critical('SMTP Authentication failed, please check SMTP credentials')
            self.logger.critical('eMail service is not available! fix the SMTP credentials and restart the service.')
        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected) as excp:
            self.logger.info('SMTP Error Details: %r', excp)
            self.logger.critical('Unable to connect to SMTP server, please check SMTP server details and network connection')
            self.logger.critical('eMail service is not available! fix the SMTP server details and restart the service.')
        except TimeoutError as excp:
            self.logger.info('SMTP Error Details: %r', excp)
            self.logger.critical('SMTP server connection timed out, please check SMTP server details and network connection')
            self.logger.critical('eMail service is not available! fix the SMTP server details (or) network and restart the service.')
        except Exception as excp:
            self.logger.exception(repr(excp))
        finally:
            self.logger.info('Closing SMTP session')
            asyncio.run(self.do_force_closure())
            # in case if we skipped _do_work due to critical failures then the interrupt & termination signal handlers
            # are mapped to sys.exit(0) which will terminate the process.
            signal.signal(signal.SIGINT, lambda _s, _f: sys.exit(0))
            signal.signal(signal.SIGTERM, lambda _s, _f: sys.exit(0))

    @staticmethod
    async def run(log_level:int = logging.DEBUG):
        global log_listener # pylint: disable=global-statement

        _que = multiprocessing.Manager().Queue(-1) # unlimited size
        log_listener = IQueueListener(_que, logging.StreamHandler(), respect_handler_level=True)
        log_listener.start()
        srvmail_logger = utils_get_logger(
            __name__,
            level=log_level,
            fmt='%(levelname)s:%(process)d:%(name)s:%(funcName)s, line %(lineno)d => %(message)s')
        try:
            assert len(SrvcEmail.self_objects.values()) > 0, 'No email service object found'

            for obj in SrvcEmail.self_objects.values():
                mail_process_tasks.append(asyncio.create_task(run.cpu_bound(obj.entry, _que, log_level)))

            srvmail_logger.debug('mail_process_tasks: {mail_process_tasks}')
            # await asyncio.wait(mail_process_tasks, timeout=1, return_when=asyncio.FIRST_EXCEPTION)
            # await asyncio.gather(*mail_process_tasks)
        except Exception as excp:
            srvmail_logger.exception(repr(excp))
            # traceback.print_exc()
        # finally:
        #     log_listener.stop()
        srvmail_logger.debug('finished')

    @staticmethod
    async def stop():
        global log_listener # pylint: disable=global-variable-not-assigned

        srvmail_logger = utils_get_logger(__name__)
        try:
            for obj in SrvcEmail.self_objects.values():
                await obj.do_force_closure()
        except Exception as excp:
            srvmail_logger.exception(repr(excp))

        # cancel all the process wrapped under asyncio.Task
        for x in mail_process_tasks: x.cancel()

        log_listener.stop()
        srvmail_logger.debug('done')
