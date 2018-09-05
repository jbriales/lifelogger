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
from googleapiclient.errors import HttpError

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

    notify2.init("lifelogger")
    # Use global try block to notify user/developer about uncaught exceptions
    try:

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
        with open(message_filename, "w") as f:
            if summary:
                f.write("%s" % summary)
            f.write("\n") # New line after summary (empty or not!)
            # Add metadata
            # From-To interval (special keywords: last, now)
            f.write("from %s to now\n" % start.strftime("%H:%M"))

            # Create empty line after summary and metadata
            f.write("\n\n")

        # Open editor for user input
        gedit_args = ['gedit', '-s', message_filename]
        if summary:
            # Summary already given
            # Add '+' to put cursor at the end of file upon opening
            gedit_args.append('+')
        call_return = subprocess.call(gedit_args)
        assert call_return is 0

        # Parse summary and description from message file
        with open(message_filename, 'r') as f:
            # Get summary from first line
            summary = f.readline().strip()
            # Get start and end times from metadata (second line)
            meta_str = f.readline().strip()
            # Read rest of file as description
            description = f.read().strip()



        # Assert summary is not empty
        if not summary:
            sys.stdout.write("Failed - Empty summary\n")
            note = notify2.Notification("ERROR in lifelogger entry",
                                        "Empty summary",
                                        os.path.join(DATA_PATH, "newnote-gray.png")
                                        )
            note.show()
            return False

        # Parse final start and end times
        r = re.compile('from (?P<start>\S+) to (?P<end>\S+)')
        try:
            times = r.match(meta_str).groupdict()
        except AttributeError as err:
            print('ERROR: No times match for %s' % meta_str)
            return False

        # Translate start time into datetime
        now = datetime.utcnow()
        if times['start'] == start.strftime("%H:%M"):
            # Same start time as originally stored
            pass
        elif times['start'] == 'last':
            # Special keyword

            # Query events from last 2 days in *lifelogger*
            last_events = service.events().list(
                calendarId=config['calendars']['lifelogger']['id'],
                timeMin=(now-timedelta(days=2)).isoformat() + "Z",
                timeMax=now.isoformat() + "Z"
            ).execute()['items']

            # Get endtimes of all retrieved events
            GetDateTime = lambda str : datetime.strptime(str, "%Y-%m-%dT%H:%M:%S")
            endtimes = [GetDateTime(event['end']['dateTime'][0:-6]) for event in last_events]

            # Keep last finished event as starting point for current event
            start = max(endtimes)
        else:
            # Parse datetime from hh:mm
            try:
                r = re.compile("(\d+):(\d+)")
                h, m = r.match(times['start']).groups()
                start = start.replace(hour=int(h), minute=int(m))
            except ValueError as exc:
                print("ERROR: Wrong start date format (should be HH:MM): %s" % times['start'])

        # Translate end time into datetime
        if times['end'] == 'now':
            # Special keyword
            end = datetime.now() + timedelta(minutes=offset)
            pass
        else:
            # Parse datetime from 'hh:mm'
            try:
                r = re.compile("(\d+):(\d+)")
                h, m = r.match(times['end']).groups()
                h = int(h)
                m = int(m)

                now = datetime.now() + timedelta(minutes=offset)
                # Correct hh:mm in end time
                end = now.replace(hour=h, minute=m)
                if h <= now.hour:
                    # Normal behavior: We are setting a time earlier than now (a corrected end time)
                    pass
                else:
                    # If user-given hour is larger than now.hour
                    # that's *probably* because now is a day later (resetting the clock!)
                    # Substract one day from the date
                    end = end - timedelta(days=1)
            except AttributeError as exc:
                error_str = "ERROR: Wrong end date format (should be HH:MM): %s" % times['end']
                print(error_str)
                note = notify2.Notification("ERROR in lifelogger entry",
                                            error_str,
                                            os.path.join(DATA_PATH, "newnote-gray.png")
                                            )
                note.show()

        # Get duration of event and notify as pop-up
        duration_str = str(end - start).split(".")[0]  # drop microseconds
        note = notify2.Notification("Finished lifelogger entry",
                                    duration_str,
                                    os.path.join(DATA_PATH, "newnote-gray.png")
                                    )
        note.show()

        # Try to delete the message file
        # try:
        #     os.remove(message_filename)
        # except OSError as e:
        #     print("Error: %s - %s." % (e.filename, e.strerror))

        result = service.events().insert(
            calendarId=config['calendars']['lifelogger']['id'],
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
            note = notify2.Notification("ERROR in lifelogger entry",
                                        "Could not create insert new entry - status %s" % result['status'],
                                        os.path.join(DATA_PATH, "newnote-gray.png")
                                        )
            note.show()
            return False

    except Exception as err:
        sys.stdout.write("Failed - Uncaught exception\n")
        sys.stdout.write(err.message)
        import traceback
        print(traceback.format_exc())
        note = notify2.Notification("ERROR in lifelogger entry",
                                    "Uncaught exception\n" + traceback.format_exc(),
                                    os.path.join(DATA_PATH, "newnote-gray.png")
                                    )
        note.show()
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


def cont_command(num_prev_events):
    """Create continuation event entry in Calendar

    :param num_prev_events: Number of previous events to display
    :return:
    """

    # Get Calendar service (entrypoint to API)
    service = connect()

    # Query events from last 2 days in *lifelogger*
    # HARDCODED: Nr of days to query
    now = datetime.utcnow()
    last_events = service.events().list(
        calendarId=config['calendars']['lifelogger']['id'],
        timeMin=(now - timedelta(days=2)).isoformat() + "Z",
        timeMax=now.isoformat() + "Z",
        orderBy="updated"  # get ordered list of events
    ).execute()['items']

    # Print list of last N events
    for idx, event in enumerate(last_events[:-(num_prev_events+1):-1]):
        # Traverse num_prev_events last items in reverse order
        # SOURCE: https://stackoverflow.com/a/509295
        # That is: From newest back
        print("%d: %s" % (idx+1, event['summary']))

    try:
        chosen_idx = input("Type event idx to continue: ")
        if chosen_idx < 1 or chosen_idx > num_prev_events:
            raise IndexError
    except Exception as exc:
        import traceback
        print("Bad index input")
        print(traceback.format_exc())
        return False

    # Parse event
    tags, title = last_events[-chosen_idx]['summary'].split(':')

    # Create modify summary with #cont keyword
    summary = "%s #cont:%s" % (tags, title)

    # Call new function
    # NOTE: Weird syntax in new_command requires passing a list
    return new_command([summary])


cont_command.parser = subparsers.add_parser(
    'cont',
    description="Same as lifelogger new, but copies summary from previous event.")
cont_command.parser.add_argument(
    'num_prev_events',
    nargs="?",
    type=int,
    default=10,
    help="Number of previous events to display.",
)
cont_command.parser.set_defaults(func=cont_command)


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

        # Store tracker metadata, keyed by Nomie id
        trackers = backup_data['trackers']
        trackers_dict = {}
        # Save human-readable label
        for tracker in trackers:
            trackers_dict[tracker['_id']] = dict()
            trackers_dict[tracker['_id']]['label'] = tracker['label']

        # Save groups trackers belong to
        groups = backup_data['meta'][1]['groups']
        # NOTE: Below is not really necessary
        # for group, ids in groups.iteritems():
        #     for tracker_id in ids:
        #         if 'groups' not in trackers_dict[tracker_id]:
        #             # ensure groups list is initialized
        #             trackers_dict[tracker_id]['groups'] = list()
        #         # add current group to list for this tracker
        #         trackers_dict[tracker_id]['groups'].append(group)

        # Set special group colors
        colors_dict = {
            'green': '2',
            'cocoa': '7'  # check log
        }

        # Support for changing the name of a tracker for a substitute
        substitutes = {}

        # Event fields: title, startdate, enddate, description
        events = backup_data['events']
        calendarEvents = []
        corruptedCount = 0
        addedCount = 0
        for event in events:
            # Extract needed data
            try:
                tracker_id = event['parent']
                trackername = trackers_dict[tracker_id]['label']
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
                event_duration = event['value']
                # Currently automatically convert lack of value to 0
                if event_duration == None:
                    event_duration = 0
                timestamp_in_millisecs = event['time']
                timestamp_in_secs = timestamp_in_millisecs / 1000.0

                # Now build event fields
                # Time stored is that of end
                enddate = datetime.fromtimestamp(timestamp_in_secs)
                # Start date is <value> seconds before the end
                startdate = enddate - timedelta(seconds=event_duration)
                duration_str = str(timedelta(seconds=event_duration)).split(".")[0]  # drop microseconds
                title = '#nomie: ' + trackername
                description = trackername + ' for ' + duration_str

                # Set event color according to group
                if tracker_id in groups['Exercise']:
                    color_id = colors_dict['green']
                else:
                    color_id = None

                toAdd = {
                    'title': title,
                    'startdate': startdate,
                    'enddate': enddate,
                    'description': description,
                    'colorId': color_id,
                    # Metadata
                    'time': timestamp_in_millisecs,
                    'tag': trackername
                }
                calendarEvents += [toAdd]
                addedCount += 1
            except:
                corruptedCount += 1
                print("Shoot! This record seems to be corrupted. Try manually adding it or fixing the file.")
                print(event)

        print("Corrupted record count: " + str(corruptedCount))
        print("Events successfully added: " + str(addedCount))

        # Add notes into corresponding event
        notes = backup_data["notes"]
        # NOTE: By construction, calendarEvents list is ordered by enddate
        endtimes = [event['enddate'] for event in calendarEvents]
        assert all(a < b for a, b in zip(endtimes, endtimes[1:]))

        event_iter = iter(calendarEvents)
        current_event = event_iter.next()
        for note in notes:
            # Advance event until timestamp is larger or raise exemption
            while current_event['time'] < note['time']:
                previous_event = current_event
                try:
                    current_event = event_iter.next()
                except StopIteration as err:
                    # End of events list reached
                    break
            # At this point, previous_event should match current note

            # Parse note value
            lines = note['value'].splitlines()
            if len(lines) < 2:
                print("Bad note value (single line? -> Empty content?): \n %s" % note['value'])
                continue
            note_header = lines[0]
            note_short = lines[1]
            note_long = '\n'.join(lines[2:])

            # Check tag
            r = re.compile('#(?P<tag>\w+) ((?P<h>\d+)h )*((?P<m>\d+)m )*((?P<s>\d+)s )*\s+at (?P<time_str>\d\d:\d\d)')
            out = r.match(note_header)
            if out is None:
                print("ERROR: Bad parsing of %s" % note_header)
            parsed_values = out.groupdict()
            assert parsed_values['tag'].lower() == previous_event['tag'].lower()

            # Add note content to event summary and description
            previous_event['title'] += " " + note_short
            previous_event['description'] += "\n"+note_long

        return calendarEvents

    # Ensure Nomie backup file exists
    if not os.path.exists(NOMIE_BACKUP_PATH):
        print("Failed - No available backup in %s" % NOMIE_BACKUP_PATH)
        return False

    # Ensure Nomie calendar id is set in config
    if 'Nomie' not in config['calendars']:
        print("Error: Calendar Nomie not available in config file")
        return False

    # Load backup file (json format)
    backup_data = json.loads(open(NOMIE_BACKUP_PATH).read())

    # Parse Nomie events into Calendar-like event list
    events = parse_events(backup_data)

    # Get Calendar service (entrypoint to API)
    service = connect()

    # Ensure Nomie calendar exists
    all_cals = service.calendarList().list().execute()['items']
    calendar_names = [cal['summary'] for cal in all_cals]
    if 'Nomie' not in calendar_names:
        from termcolor import colored
        print(colored("Warning: Nomie calendar missing, creating it!", 'yellow'))
        created_calendar = service.calendars().insert(
            body={
                'summary': 'Nomie'
            }
        ).execute()

        # Set color of calendar
        new_id = created_calendar['id']
        calendar_list_entry = service.calendarList().get(calendarId=new_id).execute()
        calendar_list_entry['colorId'] = '1' # cocoa

        updated_calendar_list_entry = service.calendarList().update(
            calendarId=new_id,
            body=calendar_list_entry
        ).execute()

        # Save id of new calendar to local config
        config['calendars']['Nomie']['id'] = created_calendar['id']

        # Get and save iCal address
        new_ical_url = input("Paste new Secret address in iCal format (from settings) --> ")
        config['calendars']['Nomie']['ical_url'] = new_ical_url

        # Ensure new config is stored
        config.save()

    # Ensure local database is up to date
    from .local import download_all
    download_all()

    # Keep only new events
    new_events = list()
    from ..database import Event
    for event in events:
        # Generate unique Nomie event Id based on data
        nomie_id = 'nomie' + event['startdate'].strftime('%Y%m%d%H%M%S')
        try:
            # If event exists, ignore this in new list
            Event.get(Event.uid == nomie_id + "@google.com")
        except Event.DoesNotExist as exc:
            # Event not found, add it to new list
            new_events.append(event)

    # Insert new Nomie events into Calendar

    new_entries_counter = 0
    for event in new_events:
        # Generate unique Nomie event Id based on data
        nomie_id = 'nomie' + event['startdate'].strftime('%Y%m%d%H%M%S')

        # TODO: Check event does not already exist
        # TODO: Maybe find last non-synced event, or iterate backwards until reaching already-synced id

        body = {
            'summary': event['title'],
            'description': event['description'],
            'start': {
                'dateTime': event['startdate'].isoformat(),
                'timeZone': config['timezone']
            },
            'end': {
                'dateTime': event['enddate'].isoformat(),
                'timeZone': config['timezone']
            },
            'id': nomie_id
        }
        # Add color option if custom color
        if event['colorId'] is not None:
            body['colorId'] = event['colorId']

        try:
            result = service.events().insert(
                calendarId=config['calendars']['Nomie']['id'],
                body=body
            ).execute()
        except HttpError as err:
            if int(err.resp['status']) == 409:
                from termcolor import colored
                print(colored("Error: event already exists, delete Nomie calendar to reset!", 'red'))
                # # Event already exists in chosen calendar
                # body['status'] = "confirmed" # set visible again
                # result = service.events().update(
                #     calendarId=config['calendars']['Nomie']['id'],
                #     eventId=body['id'],
                #     body=body
                # ).execute()
            else:
                raise

        if result['status'] == 'confirmed':
            print("Added new entry! Link: ", result['htmlLink'])
        else:
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
