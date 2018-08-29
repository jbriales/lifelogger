# coding=utf-8
"""
All commands that call the Google API service.
"""
from __future__ import absolute_import
from __future__ import print_function
import re
import sys
from datetime import datetime, timedelta

import dateutil.parser

from ..connection import connect
from ..config import config

from .parser import subparsers
import six


def quickadd(summary):
    summary = ' '.join(summary)

    service = connect()

    # Double up single-time events to be 0-length
    match = re.match(r'^\d\d:\d\d ', summary)
    if match:
        summary = match.group(0)[:-1] + '-' + summary

    # Make request
    print("Quick add >>", summary)

    result = service.events().quickAdd(
        calendarId=config['calendar_id'],
        text=summary
    ).execute()

    if result['status'] == 'confirmed':
        print("Added! Link: ", result['htmlLink'])
        return True
    else:
        sys.stdout.write("Failed :( - status %s\n" % result['status'])
        return False


quickadd.parser = subparsers.add_parser(
    'quickadd',
    description="Use 'quick-add' to add an event to your calendar - works the "
                "same as the Google Calendar web interface function, with "
                "some extensions. To add a 0-minute event at a particular "
                "time today, run with the time in 24-hour format at the "
                "start, e.g. '10:00 Coffee'."
)
quickadd.parser.add_argument(
    'summary',
    help="The summary for the event.",
    nargs='*'
)
quickadd.parser.set_defaults(func=quickadd)


def now(summary, duration):
    try:
        offset = int(summary[0])
        summary = summary[1:]
    except ValueError:
        offset = 0

    summary = ' '.join(summary)

    service = connect()

    start = datetime.now() + timedelta(minutes=offset)
    end = start + timedelta(minutes=duration)

    print("Adding %i-minute event >> %s" % (duration, summary))

    result = service.events().insert(
        calendarId=config['calendar_id'],
        body={
            'summary': summary,
            'start': {
                'dateTime': start.isoformat(),
                'timeZone': config['timezone']
            },
            'end': {
                'dateTime': end.isoformat(),
                'timeZone': config['timezone']
            }
        }
    ).execute()

    if result['status'] == 'confirmed':
        print("Added! Link: ", result['htmlLink'])
        return True
    else:
        sys.stdout.write("Failed :( - status %s\n" % result['status'])
        return False


now.parser = subparsers.add_parser(
    'now',
    description="Adds an event 'right now'.")
now.parser.add_argument(
    '-d',
    '--duration',
    type=int,
    default=0,
    help="The duration of the event (default 0)"
)
now.parser.add_argument(
    'summary',
    nargs="+",
    type=six.text_type,
    help="The summary for the event."
)
now.parser.set_defaults(func=now)


def new_command(summary):
    """Create new event entry in Calendar

    :param summary: Initial value for summary field (title)
    :return:
    """

    # Imports that are used only in this function
    """
    Keep here to make it cleaner and easier moving this command
    to its own file in the future
    """
    import subprocess
    import os
    import notify2
    from ..config import DATA_PATH, MSG_PATH

    try:
        offset = int(summary[0])
        summary = summary[1:]
    except ValueError:
        offset = 0

    summary = ' '.join(summary)

    # Get Calendar service (entrypoint to API)
    service = connect()

    start = datetime.now() + timedelta(minutes=offset)
    start_str = start.isoformat()
    message_filename = os.path.join(MSG_PATH, 'ENTRY_MSG_'+start_str)

    # Dump summary into message file
    with open(message_filename, "w") as file:
        if summary:
            file.write("%s\n\n\n" % summary)

    print("Start time: %s" % start_str)
    print("Starting new event >> %s" % (summary))

    # Open editor for user input
    call_return = subprocess.call(['gedit', '-s', message_filename, '+'])
    # NOTE: Right return should be 0

    end = datetime.now() + timedelta(minutes=offset)
    duration_str = str(end-start).split(".")[0] # drop microseconds
    print("Entry duration: %s" % duration_str)

    # Try to delete the message file
    # try:
    #     os.remove(message_filename)
    # except OSError as e:
    #     print("Error: %s - %s." % (e.filename, e.strerror))

    # Parse summary and description from message file
    with open(message_filename, 'r') as file:
        # Get summary from first line
        summary = file.readline().strip()

        # Read rest of file as description
        description = file.read().strip()

    # Assert summary is not empty
    if not summary:
        sys.stdout.write("Failed - Empty summary\n")
        return False

    # Notify duration as a pop-up
    notify2.init("lifelogger")
    note = notify2.Notification("Finished lifelogger entry",
                                duration_str,
                                os.path.join(DATA_PATH, "newnote-gray.png")
                                )
    note.show()

    result = service.events().insert(
        calendarId=config['calendar_id'],
        body={
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start.isoformat(),
                'timeZone': config['timezone']
            },
            'end': {
                'dateTime': end.isoformat(),
                'timeZone': config['timezone']
            }
        }
    ).execute()

    if result['status'] == 'confirmed':
        print("Added new entry! Link: ", result['htmlLink'])
        return True
    else:
        sys.stdout.write("Failed :( - status %s\n" % result['status'])
        return False


new_command.parser = subparsers.add_parser(
    'new',
    description="Creates a new event starting now and opens an editor for entry details.")
new_command.parser.add_argument(
    'summary',
    nargs="+",
    type=six.text_type,
    help="The summary for the event."
)
new_command.parser.set_defaults(func=new_command)


def sync_nomie():
    """Synchronize Nomie backup file with corresponding Calendar

    :return:
    """

    # Imports that are used only in this function
    """
    Keep here to make it cleaner and easier moving this command
    to its own file in the future
    """
    import os
    from ..config import NOMIE_BACKUP_PATH
    import json

    # Define function locally
    # TODO: move this to tools/nomie.py module
    def parse_events(backup_data):
        """Parse all events from Nomie backup into a list

        :param backup_data: json-like backup data
        :return: list of events data
        """

        trackers = backup_data['trackers']
        nameMap = {}
        for tracker in trackers:
            nameMap[tracker['_id']] = tracker['label']

        # Support for changing the name of a tracker for a substitute
        substitutes = {}

        events = backup_data['events']
        # Event fields: title, startdate, enddate, description, geo
        calendarEvents = []
        corruptedCount = 0
        addedCount = 0
        for event in events:
            elements = event['_id'].split('|')
            # Extract needed data
            try:
                trackername = nameMap[elements[3]]
                # Substitute tracker name if substitute is defined
                try:
                    trackername = substitutes[trackername]
                except:
                    doNothing = True

                # As Nomie 3 doesn't support spaces in tracker names, substitute with underscores
                trackername = trackername.replace(' ', '_')
                print(trackername)

                # Value should be time in seconds of the event
                # Note there is one single event for timer (at the end of timer)
                event_value = event['value']
                # Currently automatically convert lack of value to 0
                if event_value == None:
                    event_value = 0
                raw_timestamp_in_millisecs = elements[2]
                timestamp_in_secs = int(raw_timestamp_in_millisecs) / 1000.0

                # Now build event fields
                # Time stored is that of end
                enddate = datetime.fromtimestamp(timestamp_in_secs)
                # Start date is <value> seconds before the end
                startdate = enddate - timedelta(seconds=event_value)
                duration_str = str(timedelta(seconds=event_value)).split(".")[0]  # drop microseconds
                # Now save geo information without place name
                geo = '["",' + str(event['geo'][0]) + ',' + str(event['geo'][1]) + ']'
                title = '#nomie: ' + trackername
                description = trackername + ' for ' + duration_str
                toAdd = {
                    'title': title,
                    'startdate': startdate,
                    'enddate': enddate,
                    'description': description,
                    'geo': geo
                }
                calendarEvents += [toAdd]
                addedCount += 1
            except:
                corruptedCount += 1
                print("Shoot! This record seems to be corrupted. Try manually adding it or fixing the file.")
                print(event)

        print("Corrupted record count: " + str(corruptedCount))
        print("Events successfully added: " + str(addedCount))

        return calendarEvents

    # Ensure Nomie backup file exists
    if not os.path.exists(NOMIE_BACKUP_PATH):
        print("Failed - No available backup in %s" % NOMIE_BACKUP_PATH)
        return False

    # Ensure Nomie calendar id is set in config
    if 'calendar_id_nomie' not in config:
        print("Error: calendar_id_nomie field not set in config file")
        return False

    # Load backup file (json format)
    backup_data = json.loads(open(NOMIE_BACKUP_PATH).read())

    # Parse Nomie events into Calendar-like event list
    events = parse_events(backup_data)

    # Get Calendar service (entrypoint to API)
    service = connect()

    # Insert Nomie events into Calendar
    # TODO: Ensure events do not already exist in destination Calendar

    new_entries_counter = 0
    for event in events:
        # TODO: Generate unique Nomie event Id for OPTIONAL Calendar Id
        # TODO: Check event does not already exist
        # TODO: Maybe find last non-synced event, or iterate backwards until reaching already-synced id

        result = service.events().insert(
            calendarId=config['calendar_id_nomie'],
            body={
                'summary': event['title'],
                'description': event['description'],
                'start': {
                    'dateTime': event['startdate'].isoformat(),
                    'timeZone': config['timezone']
                },
                'end': {
                    'dateTime': event['enddate'].isoformat(),
                    'timeZone': config['timezone']
                }
            }
        ).execute()

        if result['status'] != 'confirmed':
            sys.stdout.write("Failed :( - status %s\n" % result['status'])
            return False

        new_entries_counter += 1

    print("Added %d new entries!" % new_entries_counter)
    return True


sync_nomie.parser = subparsers.add_parser(
    'sync-nomie',
    description="Synchronize Nomie backup events to its own Calendar.")
sync_nomie.parser.set_defaults(func=sync_nomie)


def for_command(duration, summary):
    summary = ' '.join(summary)

    service = connect()

    times = [
        datetime.now(),
        datetime.now() + timedelta(minutes=duration)
    ]
    times.sort()
    start, end = times

    print("Adding %i-minute event >> %s" % (abs(duration), summary))

    result = service.events().insert(
        calendarId=config['calendar_id'],
        body={
            'summary': summary,
            'start': {
                'dateTime': start.isoformat(),
                'timeZone': config['timezone']
            },
            'end': {
                'dateTime': end.isoformat(),
                'timeZone': config['timezone']
            }
        }
    ).execute()

    if result['status'] == 'confirmed':
        print("Added! Link: ", result['htmlLink'])
        return True
    else:
        sys.stdout.write("Failed :( - status %s\n" % result['status'])
        return False


for_command.parser = subparsers.add_parser(
    'for',
    description="Adds an event that lasts *for* the specified number of "
                "minutes, relative to now."
)
for_command.parser.add_argument(
    'duration',
    type=int,
    help="The duration of the event. Give a negative number, and the event "
         "will be set to have started 'duration' minutes ago, and end now; "
         "otherwise it starts now and ends in 'duration' minutes time."
)
for_command.parser.add_argument(
    'summary',
    help="The summary for the event.",
    nargs='*'
)
for_command.parser.set_defaults(func=for_command)


def add(summary, start=None, end=None, duration=None):
    summary = ' '.join(summary)

    if start is None:
        start = datetime.now()
    else:
        start = dateutil.parser.parse(start)

    if end is not None:
        end = dateutil.parser.parse(end)

    if duration is None:
        duration = 0

    if end is None:
        end = start + timedelta(minutes=duration)

    service = connect()

    times = [start, end]
    times.sort()
    start, end = times

    duration = (end - start).total_seconds() / 60

    print("Adding {length}-minute event at {start} >> {summary}".format(
        length=abs(duration),
        start=start,
        summary=summary
    ))

    result = service.events().insert(
        calendarId=config['calendar_id'],
        body={
            'summary': summary,
            'start': {
                'dateTime': start.isoformat(),
                'timeZone': config['timezone']
            },
            'end': {
                'dateTime': end.isoformat(),
                'timeZone': config['timezone']
            }
        }
    ).execute()

    if result['status'] == 'confirmed':
        print("Added! Link: ", result['htmlLink'])
        return True
    else:
        sys.stdout.write("Failed :( - status %s\n" % result['status'])
        return False


add.parser = subparsers.add_parser(
    'add',
    description="Generic event adding command, with all the bells and "
                "whistles."
)
add.parser.add_argument(
    '-s',
    '--start',
    default=None,
    help="The start time for the event - default is now."
)
add.parser.add_argument(
    '-e',
    '--end',
    default=None,
    help="The end time for the event - default is to make a 0-minute event."
)
add.parser.add_argument(
    '-d',
    '--duration',
    default=None,
    type=int,
    help="The duration, in minutes, for the event. If both end and duration "
         "are set, duration overrides. Can be negative."
)
add.parser.add_argument(
    'summary',
    help="The summary for the event.",
    nargs='*'
)
add.parser.set_defaults(func=add)
