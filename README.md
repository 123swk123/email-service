# eMail service for [nicegui](nicegui.io) python web ui framework

-----

## Table of Contents

- [Introduction](#introduction)
- [Installation](#installation)
- [License](#license)

## Introduction

An out of process e-mail service module using Redis/Dragonfly for nicegui [python]

![eMail service module architecture](docs\architecture.png)

Runs SMTP based eMail delivery service in a separate process, ensuring nicegui UI loop is not blocked.

We use Redis/Dragonfly in-memory cache DB's publish & subscription for inter-process communication.

Typically, a web service used to send different kinds of emails from simple user notifications to complex functional things.
so one can categorize those emails and even group them into sub-categories like `email.notify.welcome`, `email.notify.login_access` & `email.file.upload`

Imagine we convert this each sub-category into channels by which web app will inform Email service (running on separate process) to send emails. Each category we can be mapped on single process this way we can load balance and at times this can help us to send high priority emails right away without getting affected by huge list of low priority notification emails.

### API
1. Number of process we spin out is one-to-one mapped to every object instance we create
2. Number of email channels, this is controlled by `register_email_channel(self, ch_name:str, ch_mssg_conv: Callable[[bytes | bytearray], EmailMessage])` member function
3. `SrvcEmail.run()`, a static method that setup the out of process and start listening for the the email request as per above configuration as performed in 1 & 2
4. `SrvEmail.stop`, static method stops and shutdown's all previously launched out of process.
5. `entry()`, member function for internal use, basically it prepares the self object for an out of process execution
6. `do_force_closure()`, member function for internal use

### Examples

### Environment variable setup
#### Can use .env file
```env
SMTP_HOST = swk-server-2.local
SMTP_PORT = 30025
SMTP_STARTTLS = True
SMTP_FROM_EMAIL = 'hello@test.com'
SMTP_USERNAME = 'admin'
SMTP_PASSWORD = 'testpassword'
SMTP_KEEP_ALIVE_INTERVAL = 30
SMTP_DEBUG = False
```

#### Case 1, create one process and register 2 mail channels

```python
from nicegui import ui, app
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

FROM_EMAIL = os.getenv('FROM_EMAIL', 'hello@test.com')
SERVICE_NAME = os.getenv('SERVICE_NAME', 'WebService')
EMAIL_FOOTER = f'\n\n~~ {SERVICE_NAME} Admin ~~\nAn auto-generated email @ {time.strftime('%Y-%m-%d %H:%M:%S +%Z')}\nplease do not reply.'

def gen_email_welcome(val: bytes | bytearray) -> EmailMessage:
    msg = EmailWelcome.model_validate_json(val)
    rtn = EmailMessage()
    rtn['Subject'] = f'Welcome to {SERVICE_NAME}! [do not reply]'
    rtn['From'] = FROM_EMAIL
    rtn['To'] = msg.to
    rtn.set_content(f'''\
Hi {msg.full_name},

Welcome to {SERVICE_NAME}!

We are pleased to have you as a member of our {SERVICE_NAME}

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

with SrvcEmail('cache.local') as obj:
    obj.register_email_channel('email.notify.welcome', gen_email_welcome)
    obj.register_email_channel('email.notify.login_access', gen_email_login_access)

app.on_startup(SrvcEmail.run)

inpEmail = ui.input('Email:').props('type="email"')
inpFullName = ui.input('Full Name:')

async def on_click_welcome():
    msg = EmailWelcome(to=inpEmail.value, full_name=inpFullName.value, password='olQHWVrH$8').model_dump_json()
    rslt = await Redis(host='cache.local').publish('email.notify.welcome', msg)

async def on_click_login(e: nicegui.events.ClickEventArguments):
    ip = e.client.ip or 'unknown-ip'
    msg = EmailLoginAccess(to=inpEmail.value, full_name=inpFullName.value, ip_address=ip, is_access_granted=True).model_dump_json()
    rslt = await Redis(host='cache.local').publish('email.notify.login_access', msg)

with ui.grid(rows=2, columns=4):
    ui.button('Welcome e-Mail', on_click=on_click_welcome)
    ui.button('Login e-Mail', on_click=on_click_login)

ui.run(host='localhost', show=False)
```
#### Case 2, create two process and register 2 mail channels in each process

```python
from nicegui import app

with SrvcEmail('cache.local') as obj:
    obj.register_email_channel('email.notify.welcome', gen_email_welcome)
    obj.register_email_channel('email.notify.login_access', gen_email_login_access)
with SrvcEmail('cache.local') as obj:
    obj.register_email_channel('email.file.upload', gen_email_upload)
    obj.register_email_channel('email.file.download', gen_email_download)

app.on_startup(SrvcEmail.run)
```

## Installation

```console
pip install email-service-nicegui
```

## FAQs
- Use fake SMTP server for testing eMail service, preferably run it as a Docker container
  - [MailHog - Simple setup](https://github.com/mailhog/MailHog)
    ```shell
    docker run --rm -d -p 30025:1025 -p 30080:8025 mailhog/mailhog
    ```
  - [smtp4dev - with TLS support](https://github.com/rnwood/smtp4dev)
    ```shell
    docker run --rm -d -p 30080:80 -p 30025:25 rnwood/smtp4dev
    ```

## License

`email-service-nicegui` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
