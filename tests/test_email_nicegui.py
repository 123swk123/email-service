# SPDX-FileCopyrightText: 2024-present SwK <swk@swkemb.com>
#
# SPDX-License-Identifier: MIT

# pylint: disable=missing-module-docstring, missing-function-docstring, missing-class-docstring, line-too-long, broad-except

import nicegui.events
from nicegui import app, ui
from redis.asyncio import Redis

# import test_email_redis_common
from test_email_redis_common import (
    EEmailChannel,
    EmailAccountRemoval,
    EmailLoginAccess,
    EmailWelcome,
    gen_email_account_removal,
    gen_email_login_access,
    gen_email_welcome,
)

from email_service_nicegui import SrvcEmail

REDIS_HOST = 'cache.local'

with SrvcEmail(REDIS_HOST) as obj_tmp:
    obj_tmp.register_email_channel(EEmailChannel.WELCOME, gen_email_welcome)
    obj_tmp.register_email_channel(EEmailChannel.LOGIN_ACCESS, gen_email_login_access)
with SrvcEmail(REDIS_HOST) as obj_tmp:
    obj_tmp.register_email_channel(EEmailChannel.ACCOUNT_REMOVAL, gen_email_account_removal)

app.on_startup(SrvcEmail.run)
app.on_shutdown(SrvcEmail.stop)

inpEmail = ui.input('Email:', value='someone@test.co').props('type="email"')
inpFullName = ui.input('Full Name:', value='Crazy Doe')

async def on_click_welcome():
    rconn = Redis(host=REDIS_HOST)
    msg = EmailWelcome(to=inpEmail.value, full_name=inpFullName.value, password='olQHWVrH$8').model_dump_json()
    rslt = await rconn.publish(EEmailChannel.WELCOME, msg)
    print('email sent:', rslt)

async def on_click_login(e: nicegui.events.ClickEventArguments):
    rconn = Redis(host=REDIS_HOST)
    ip = e.client.ip or 'unknown-ip'
    msg = EmailLoginAccess(to=inpEmail.value, full_name=inpFullName.value, ip_address=ip, is_access_granted=True).model_dump_json()
    rslt = await rconn.publish(EEmailChannel.LOGIN_ACCESS, msg)
    print('email sent:', rslt)

async def on_click_removal():
    rconn = Redis(host=REDIS_HOST)
    msg = EmailAccountRemoval(to=inpEmail.value, full_name=inpFullName.value).model_dump_json()
    rslt = await rconn.publish(EEmailChannel.ACCOUNT_REMOVAL, msg)
    print('email sent:', rslt)

with ui.grid(rows=2, columns=4):
    ui.button('Welcome e-Mail', on_click=on_click_welcome)
    ui.button('Login e-Mail', on_click=on_click_login)
    ui.button('Account Removal e-Mail', on_click=on_click_removal)

ui.run(host='localhost', show=False, uvicorn_logging_level='info')
