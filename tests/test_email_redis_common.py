# SPDX-FileCopyrightText: 2024-present SwK <swk@swkemb.com>
#
# SPDX-License-Identifier: MIT

import os
import time

# pylint: disable=missing-module-docstring, missing-function-docstring, missing-class-docstring, line-too-long, broad-except
from email.message import EmailMessage
from enum import StrEnum
from typing import List

from pydantic import BaseModel


class EmailWelcome(BaseModel):
    to: str
    full_name: str
    password: str

class EmailLoginAccess(BaseModel):
    to: str
    full_name: str
    ip_address: str
    is_access_granted: bool

class EmailAccountRemoval(BaseModel):
    to: str
    full_name: str

class EEmailChannel(StrEnum):
    WELCOME = 'email.notify.welcome'
    LOGIN_ACCESS = 'email.notify.login_access'
    ACCOUNT_REMOVAL = 'email.notify.account_removal'

FROM_EMAIL = os.getenv('SMTP_FROM_EMAIL', 'hello@test.com')
SERVICE_NAME = os.getenv('SERVICE_NAME', 'FileServer')
EMAIL_FOOTER = f'\n\n~~ {SERVICE_NAME} Admin ~~\nAn auto-generated email @ {time.strftime('%Y-%m-%d %H:%M:%S +%Z')}\nplease do not reply.'

def gen_email_welcome(val: bytes | bytearray) -> EmailMessage:
    msg = EmailWelcome.model_validate_json(val)
    rtn = EmailMessage()
    rtn['Subject'] = f'Welcome to {SERVICE_NAME}! [do not reply]'
    rtn['From'] = FROM_EMAIL
    rtn['To'] = msg.to
    rtn.set_content(f'''\
Hi {msg.full_name},

Welcome to FileServer!

We are pleased to have you as a member of our FileServer, A file sharing/collaboration platform

your initial login password set as below, please change it after login:

{msg.password}''' + EMAIL_FOOTER)
    return rtn

def gen_email_login_access(val: bytes | bytearray) -> EmailMessage:
    msg = EmailLoginAccess.model_validate_json(val)
    rtn = EmailMessage()
    rtn['Subject'] = f'{SERVICE_NAME} Login Access Notification [do not reply]'
    rtn['From'] = FROM_EMAIL
    rtn['To'] = msg.to
    rtn.set_content(f'''\
Hi {msg.full_name},

IP Address: {msg.ip_address}

Your recent login attempt {'was successful' if msg.is_access_granted else 'failed'}.''' + EMAIL_FOOTER)
    return rtn

def gen_email_account_removal(val: bytes | bytearray) -> EmailMessage:
    msg = EmailAccountRemoval.model_validate_json(val)
    rtn = EmailMessage()
    rtn['Subject'] = f'{SERVICE_NAME} Account Removal Notification [do not reply]'
    rtn['From'] = FROM_EMAIL
    rtn['To'] = msg.to
    rtn.set_content(f'''\
Hi {msg.full_name},

Your account has been removed from {SERVICE_NAME} by Admin, for further details please contact Administrator.''' + EMAIL_FOOTER)
    return rtn
