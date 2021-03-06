# coding=utf-8
"""
All commands that create & use the local copies of the Google Calendar data.
"""
from __future__ import absolute_import, print_function

import requests

from icalendar import Calendar
from termcolor import colored

from ..config import config, ICAL_PATH, ICS_PATH
from ..utils import nice_format

from .parser import subparsers
import six
from six.moves import input


def download_all():

    import os

    # if not name:
    #     # Download all calendars
    #     for cal in config['calendars']:
    #         download()

    for cal_name, meta in config['calendars'].items():
        print("Downloading private iCal file for %s..." % cal_name)
        ical_url = meta['ical_url']
        req = requests.get(ical_url, stream=True)

        if req.status_code != 200:
            print("Could not fetch iCal url for %s - has it expired? " % cal_name)
            print("Change config field")
            print(ical_url)
            return False

        ics_path = os.path.join(ICS_PATH, "%s.ics" % cal_name)
        with open(ics_path, 'wb') as f:
            for chunk in req.iter_content():
                f.write(chunk)

        print("Download successful!")

    make_db_all()

    return True


download_all.parser = subparsers.add_parser(
    'download_all',
    description="Downloads the iCal that contains the whole of your Google "
                "Calendar, for all registered calendars,"
                "and then parses them into the local database"
)
download_all.parser.set_defaults(func=download_all)


def make_db_all():
    from ..database import Event, db
    import os

    print("Converting iCal files into sqlite database...")

    try:
        Event.drop_table()
    except Exception:
        pass

    try:
        Event.create_table()
    except Exception:
        pass

    for cal_name in config['calendars']:
        ics_path = os.path.join(ICS_PATH, "%s.ics" % cal_name)

        with open(ics_path, 'rb') as f:
            ical_data = f.read()

        cal = Calendar.from_ical(ical_data)

        with db.atomic():
            for event in cal.walk("VEVENT"):
                Event.create_from_ical_event(cal_name, event)

    print("Imported {} events.".format(
        Event.select().count()
    ))

    return True


make_db_all.parser = subparsers.add_parser(
    'make_db_all',
    description="Parses all the downloaded iCal file into the local sqlite "
                "database. Normally done when the download command is run, "
                "but may need re-running on changes to lifelogger."
)
make_db_all.parser.set_defaults(func=make_db_all)


def create_md_from_ical_event(calendar_name, ical_event):
    start = normalized(ical_event.get('dtstart').dt)
    end = ical_event.get('dtend')

    # 0-minute events have no end
    if end is not None:
        end = normalized(end.dt)
    else:
        end = start

    return cls.create(
        calendar=calendar_name,
        uid=ical_event.get('uid'),
        summary=ical_event.get('summary'),
        start=start,
        end=end,
        description=ical_event.get('description', ''),
    )


def make_mdnotes_from_search():
    import os

    print("Converting search events in iCal file into md notes...")

    # Create temporary folder for markdown notes
    tmp_path = os.path.expanduser("~/tmp/search")
    if not os.path.exists(tmp_path):
        try:
            os.makedirs(tmp_path)
        except OSError as exc:  # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise

    for cal_name in ['lifelogger']:  # Read only from lifelogger
        ics_path = os.path.join(ICS_PATH, "%s.ics" % cal_name)

        with open(ics_path, 'rb') as f:
            ical_data = f.read()

        cal = Calendar.from_ical(ical_data)
        for event in cal.walk("VEVENT"):
            # Use original uid from Google (remove suffix)
            uid = str(event.get('uid')).replace('@google.com', '.md')
            # Remove tag from title
            summary = str(event.get('summary'))
            if '#search: ' not in summary:
                continue
            title = summary.replace('#search: ', '') + '.md'
            try:
                with open(os.path.join(tmp_path, title), 'w') as f:
                    f.write(event.get('description'))
            except:
                print(colored("ERROR: Saving %s" % title), 'red')

    return True


make_mdnotes_from_search.parser = subparsers.add_parser(
    'make_mdnotes_from_search',
    description="Parses all the downloaded iCal file into markdown notes. "
)
make_mdnotes_from_search.parser.set_defaults(func=make_mdnotes_from_search)


def download(reset=None):

    if reset:
        config.pop('ical_url[Nomie]', None)

    try:
        ical_url = config['ical_url[Nomie]']
    except KeyError:
        print("To download the iCal file for analysis, you must give me the "
              "public URL for it.")
        print("Please go to the Google Calendar web interface "
              ", 'Calendar Settings', and then copy the link address from "
              "the ICAL button under 'Calendar Address'")
        ical_url = input("Paste --> ")
        config['ical_url[Nomie]'] = ical_url

    print("Downloading private iCal file...")
    req = requests.get(ical_url, stream=True)

    if req.status_code != 200:
        print("Could not fetch iCal url - has it expired? ")
        print("To change, run download --reset")
        print(ical_url)
        return False

    with open(ICAL_PATH, 'wb') as f:
        for chunk in req.iter_content():
            f.write(chunk)

    print("Download successful!")

    make_db()

    return True


download.parser = subparsers.add_parser(
    'download',
    description="Downloads the iCal that contains the whole of your Google "
                "Calendar, and then parses it into the local database"
)
download.parser.add_argument(
    '-r',
    '--reset',
    const=True,
    default=False,
    nargs='?',
    help="Pass this in to force re-pasting in the iCal url, if e.g. the url "
         " stored in lifelogger is no longer valid."
)
download.parser.set_defaults(func=download)


def make_db():
    from ..database import Event, db

    print("Converting iCal file into sqlite database...")

    with open(ICAL_PATH, 'rb') as f:
        ical_data = f.read()

    cal = Calendar.from_ical(ical_data)

    try:
        Event.drop_table()
    except Exception:
        pass

    try:
        Event.create_table()
    except Exception:
        pass

    with db.atomic():
        for event in cal.walk("VEVENT"):
            Event.create_from_ical_event(event)

    print("Imported {} events.".format(
        Event.select().count()
    ))

    return True


make_db.parser = subparsers.add_parser(
    'make_db',
    description="Parses the downloaded iCal file into the local sqlite "
                "database. Normally done when the download command is run, "
                "but may need re-running on changes to lifelogger."
)
make_db.parser.set_defaults(func=make_db)


def shell():
    from datetime import datetime, date  # noqa
    from ..database import Event, regexp, db  # noqa

    from IPython import embed
    embed()


shell.parser = subparsers.add_parser(
    'shell',
    description="Loads the local database and an IPython shell so you can "
                "manually search around the events using the 'peewee' ORM."
)
shell.parser.set_defaults(func=shell)


def sql(statement, separator):
    from ..database import conn
    statement = ' '.join(statement)

    cursor = conn.cursor()
    cursor.execute(statement)

    separator = {
        'comma': ',',
        'semicolon': ';',
        'tab': '\t',
    }[separator]

    # Header
    print(separator.join([d[0] for d in cursor.description]))

    # Data
    for row in cursor.fetchall():
        print(separator.join([str(v) for v in row]))


sql.parser = subparsers.add_parser(
    'sql',
    description="Execute a SQL statement direct on the db and output results "
                "as csv."
)
sql.parser.add_argument(
    'statement',
    nargs="+",
    type=six.text_type,
    help="The SQL statement."
)
sql.parser.add_argument(
    '-s',
    '--separator',
    nargs="?",
    type=six.text_type,
    default="comma",
    choices=['comma', 'semicolon', 'tab'],
    help="Separator for the output - default comma."
)
sql.parser.set_defaults(func=sql)


def list_command(filter_re):
    filter_re = ' '.join(filter_re)
    from ..database import Event, regexp

    events = Event.select().where(regexp(Event.summary, filter_re))
    # events = Event.select().where(regexp(Event.description, filter_re))

    for event in events:
        print(event.display()+'\n')

    return True


list_command.parser = subparsers.add_parser(
    'list',
    description="Lists the events that match a given regex."
)
list_command.parser.add_argument(
    'filter_re',
    nargs="+",
    type=six.text_type,
    help="The regex to filter events by."
)
list_command.parser.set_defaults(func=list_command)


def csv(filter_re, separator, varnames):
    filter_re = ' '.join(filter_re)

    varnames = varnames.split(',')

    separator = {
        'comma': ',',
        'semicolon': ';',
        'tab': '\t',
    }[separator]

    from ..database import Event, regexp

    events = Event.select().where(regexp(Event.summary, filter_re))

    # Header
    print(separator.join(varnames))

    # Data
    for event in events:
        print(separator.join([
            nice_format(event.get_var(varname)) for varname in varnames
        ]))


csv.parser = subparsers.add_parser(
    'csv',
    description="Used to output properties of events that a given filter as "
                "CSV data."
)
csv.parser.add_argument(
    '-s',
    '--separator',
    nargs="?",
    type=six.text_type,
    default="comma",
    choices=['comma', 'semicolon', 'tab'],
    help="Separator for the output - default comma."
)
csv.parser.add_argument(
    '-v',
    '--varnames',
    nargs="?",
    type=six.text_type,
    default="start,end,summary",
    help="A comma-separated list of the Event variables to output (options: "
         "start, end, summary, duration_seconds, duration_minutes, "
         "duration_hours, units, percentage, kg, mg). "
         "Defaults to 'start,end,summary'."
)
csv.parser.add_argument(
    'filter_re',
    nargs="+",
    type=six.text_type,
    help="The regex to filter events by."
)
csv.parser.set_defaults(func=csv)
