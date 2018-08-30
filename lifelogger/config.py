# coding=utf-8
from __future__ import absolute_import, print_function

import json
import os

from collections import MutableMapping

DATA_PATH = os.path.expanduser("~/.config/lifelogger/")
MSG_PATH = os.path.join(DATA_PATH, "msg")
ICS_PATH = os.path.join(DATA_PATH, "ics")
CONFIG_PATH = os.path.join(DATA_PATH, "config.json")
ICAL_PATH = os.path.join(DATA_PATH, "calendar.ics")
DB_PATH = os.path.join(DATA_PATH, "calendar.sqlite")

# Setup paths for Nomie
NOMIE_PATH = os.path.expanduser("~/Dropbox/Apps/Nomie/")
NOMIE_BACKUP_FILE = "Android-Moto_G_(4)-1980787128.nomie.json"
NOMIE_BACKUP_PATH = os.path.join(NOMIE_PATH, NOMIE_BACKUP_FILE)

# Ensure dotfile data folder exists for lifelogger
if not os.path.exists(DATA_PATH):
    try:
        os.makedirs(DATA_PATH)
    except OSError as exc:  # Guard against race condition
        if exc.errno != errno.EEXIST:
            raise

# Ensure subfolder for temporary message file exists
if not os.path.exists(MSG_PATH):
    try:
        os.makedirs(MSG_PATH)
    except OSError as exc:  # Guard against race condition
        if exc.errno != errno.EEXIST:
            raise

# Ensure subfolder for temporary ics files exists
if not os.path.exists(ICS_PATH):
    try:
        os.makedirs(ICS_PATH)
    except OSError as exc:  # Guard against race condition
        if exc.errno != errno.EEXIST:
            raise


class ConfigDict(MutableMapping):

    def __init__(self, path):
        self._path = path
        self._loaded = False
        self._data = {}

    def _load(self):
        try:
            with open(self._path) as cfile:
                self._data.update(json.load(cfile))
        except IOError:
            print("(Config file {} missing - creating afresh)".format(self._path))
        except ValueError:
            raise ValueError("Config file {} corrupt!".format(self._path))

        self._loaded = True

    def _save(self):
        if not os.path.exists(DATA_PATH):
            os.makedirs(DATA_PATH)

        with open(CONFIG_PATH, 'w') as cfile:
            cfile.write(json.dumps(self._data, indent=2))

    def save(self):
        """Force save manually
        """
        self._save()

    def __getitem__(self, key):
        if not self._loaded:
            self._load()
        return self._data[key]

    def __setitem__(self, key, value):
        if not self._loaded:
            self._load()

        self._data[key] = value

        self._save()

    def __delitem__(self, key):
        if not self._loaded:
            self._load()

        del self._data[key]

        self._save()

    def __len__(self):
        return len(self._data)

    def __iter__(self):
        return iter(self._data)


config = ConfigDict(CONFIG_PATH)
