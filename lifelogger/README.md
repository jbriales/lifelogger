lifelogger blocks
=================

# main.py
Parse right function and call on other arguments
Program uses [argparse](https://docs.python.org/3/library/argparse.html)

# config.py
- Defines global variables (e.g. paths for config files),
- Ensures these paths exist,
- Defines `class ConfigDict(MutableMapping)`

# connection.py
Handles connecting to Google API and authenticating.
It relies on the oauth2client library,
see [API doc](https://developers.google.com/api-client-library/python/guide/aaa_oauth) for basic details.

## Basics of connect() and oauth2client
The main elements in connect are:
- Obtaining credentials (if not done yet) via `oauth2client` package
  - key element: `FLOW`
- Build a Google Calendar service via `apiclient` (alias for `googleapiclient`)

# Code details

- commands/parser.py:
  Define main parser and declares subparsers object
- commands/local.py:
  Define subparsers that act locally
- commands/google.py:
  Commands that call the Google API service
