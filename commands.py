# coding=utf-8
import argparse
import re
import sys
from datetime import datetime, timedelta


parser = argparse.ArgumentParser()
subparsers = parser.add_subparsers()


def quickadd(summary):
    import connection
    from config import config

    service = connection.connect()

    # Double up single-time events to be 0-length
    match = re.match(r'^\d\d:\d\d ', summary)
    if match:
        summary = match.group(0)[:-1] + '-' + summary

    # Make request
    print "Quick add >>", summary

    result = service.events().quickAdd(
        calendarId=config['calendar_id'],
        summary=summary
    ).execute()

    if result['status'] == 'confirmed':
        print "Added! Link: ", result['htmlLink']
        return True
    else:
        sys.stdout.write("Failed :( - status %s\n" % result['status'])
        return False

parser_quickadd = subparsers.add_parser('quickadd')
parser_quickadd.add_argument('summary')
parser_quickadd.set_defaults(func=quickadd)


def now(summary, offset=0):
    import connection
    from config import config

    service = connection.connect()

    when = datetime.now() + timedelta(minutes=offset)

    print "Adding 0-minute event >>", summary

    result = service.events().insert(
        calendarId=config['calendar_id'],
        body={
            'summary': summary,
            'start': {
                'dateTime': when.isoformat(),
                'timeZone': config['timezone']
            },
            'end': {
                'dateTime': when.isoformat(),
                'timeZone': config['timezone']
            }
        }
    ).execute()

    if result['status'] == 'confirmed':
        print "Added! Link: ", result['htmlLink']
        return True
    else:
        sys.stdout.write("Failed :( - status %s\n" % result['status'])
        return False

parser_now = subparsers.add_parser('now')
parser_now.add_argument('offset', type=int, default=0, nargs='?')
parser_now.add_argument('summary')
parser_now.set_defaults(func=now)
