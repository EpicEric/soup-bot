"""
This file was an attempt at using spaCy to parse times, but not only was it
ridiculously complex, it didn't run on my RPi, so I just left this code for
historical purposes.
"""

import datetime
import dateparser
import dateutil.parser
import logging
import re
import spacy

nlp = None

ENT_LABEL_DATE = 391
ENT_LABEL_TIME = 392
ENT_LABEL_CARDINAL = 397

RE_TIME_RANGE = re.compile(r"(?:between )?([0-9:h]+) ?(?:-|to|till|until|and) ?([0-9:h]+) ?(am|pm)?", re.I)
RE_HOUR_WITH_OPTIONAL_MINUTES = re.compile(r"[a-z]*? ?(2[0-4]|[0-1]?[0-9])(?:[ \:h])?([0-5][0-9])?(?:[ \:h]?[0-5][0-9])? ?(am|pm)?", re.I)

SPECIAL_TIMES = ['noon', 'midnight']


class ProcessTimeMessageException(ValueError):
  pass


def init():
  global nlp
  nlp = spacy.load('en_core_web_trf')

def process_time_message(message, local_datetime, tz):
  if not nlp:
    raise ValueError('NLP not initialized!')

  doc = nlp(message)

  #return [(ent.start, ent.text, ent.label_) for ent in doc.ents]

  date_assumption = None

  data_to_parse = {
    # Normally a date but may include values that count as time. If there's a single date, it'll be used as a parameter for all times
    'date': [],
    # Should always be a time identified by NLP. This takes top priority as the value to be translated. May also include time ranges, which should be split up
    'time': [],
    # Last priority; times that may have been mistaken as cardinals by NLP. Ignored unless time doesn't have any values
    'cardinal': [],
  }

  for ent in doc.ents:
    if ent.label == ENT_LABEL_DATE:
      # Make sure it's not a time in disguise
      if RE_HOUR_WITH_OPTIONAL_MINUTES.fullmatch(ent.text):
        data_to_parse['time'].append(ent.text)
      else:
        data_to_parse['date'].append(ent.text)
    elif ent.label == ENT_LABEL_TIME:
      # Split time ranges if necessary
      re_match = RE_TIME_RANGE.match(ent.text)
      if re_match:
        data_to_parse['time'].append(f'{re_match[1]}{re_match[3] if re_match[3] else ""}')
        data_to_parse['time'].append(f'{re_match[2]}{re_match[3] if re_match[3] else ""}')
      else:
        data_to_parse['time'].append(ent.text)
    elif ent.label == ENT_LABEL_CARDINAL:
      data_to_parse['cardinal'].append(ent.text)

  # Check if a single date is mentioned and use that as our basis
  processed_date = local_datetime
  explicit_date = False
  parsed_date = None
  if len(data_to_parse['date']) > 1:
    multiple_dates_string = '", "'.join(data_to_parse['date'])
    raise ProcessTimeMessageException(f'There are too many dates ("{multiple_dates_string}") to figure out which one the message refers to!')
  elif len(data_to_parse['date']) == 1:
    unprocessed_date = data_to_parse['date'][0]
    try:
      parsed_date = dateutil.parser.parse(unprocessed_date, fuzzy=True, ignoretz=True)
    except dateutil.parser.ParserError:
      pass
    if not parsed_date:
      parsed_date = dateparser.parse(unprocessed_date, settings={'RELATIVE_BASE': local_datetime, 'PREFER_DATES_FROM': 'future'})
    if parsed_date:
      explicit_date = True
      processed_date = parsed_date.replace(tzinfo=tz)
      date_assumption = f'the date "{unprocessed_date}" is on {parsed_date.strftime("%b %e")}'
    else:
      # TODO: More handlers for dates that no-one can identify
      logging.warning(f'Unable to parse date "{unprocessed_date}"')

  results_data = {}

  # Convert times
  for k in ('time', 'cardinal'):
    results_data[k] = []
    for time in data_to_parse[k]:
      time_lower = time.lower()
      time_values = []
      cardinal_assumption = f'"{time}" is an hour' if k == 'cardinal' else None
      calculated_hour = processed_date.time().hour
      re_match = RE_HOUR_WITH_OPTIONAL_MINUTES.match(time)
      if not re_match and k == 'time' and time_lower not in SPECIAL_TIMES:
        # Couldn't process it the normal way; log and ignore
        logging.error('Failed to process time "%s"! Original text: "%s"', time, message)
        continue
      hour = int(re_match[1]) if re_match and re_match[1] else 0
      minute = int(re_match[2]) if re_match and re_match[2] else 0
      am_pm = re_match[3].upper() if re_match and re_match[3] else None
      # Special times
      if time_lower == 'noon':
        hour = 12
        minute = 0
      if time_lower == 'midnight':
        hour = 24
        minute = 0
      if (hour, minute) == (24, 0):
        # Has to be a full day after specific date
        if explicit_date:
          time_values.append({'datetime': processed_date.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1), 'assumptions': []})
        # Has to be a full day after an unspecified date. Assume tomorrow
        else:
          time_values.append({'datetime': processed_date.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1), 'assumptions': [f'"{time}" is today'] if parsed_date else []})
      elif hour >= 24:
        # Probably a cardinal that doesn't fit as an hour, ignore
        continue
      elif hour > 12 or am_pm == 'PM':
        if hour < 12:
          hour += 12
        # Has to be PM of specific date
        if explicit_date:
          time_values.append({'datetime': processed_date.replace(hour=hour, minute=minute, second=0, microsecond=0), 'assumptions': []})
        # Has to be PM, but we don't know the date. Assume today
        else:
          time_values.append({'datetime': processed_date.replace(hour=hour, minute=minute, second=0, microsecond=0), 'assumptions': [f'"{time}" is today'] if parsed_date else []})
      elif am_pm == 'AM':
        if hour == 12:
          hour = 0
        # Has to be AM of specific date
        if explicit_date:
          time_values.append({'datetime': processed_date.replace(hour=hour, minute=minute, second=0, microsecond=0), 'assumptions': []})
        # Has to be AM, but we don't know the date. Assume today
        else:
          time_values.append({'datetime': processed_date.replace(hour=hour, minute=minute, second=0, microsecond=0), 'assumptions': [f'"{time}" is today'] if parsed_date else []})
      else:
        # It's 5PM and I say 7, it may mean 7AM or 7PM of the same day. Prioritize afternoon
        if calculated_hour < hour + 12:
          time_values.append({'datetime': processed_date.replace(hour=hour, minute=minute, second=0, microsecond=0) + datetime.timedelta(hours=12), 'assumptions': [f'"{time}" is PM', ]})
          time_values.append({'datetime': processed_date.replace(hour=hour, minute=minute, second=0, microsecond=0), 'assumptions': [f'"{time}" is AM']})
        # It's 5AM and I say today at 7, it may mean 7AM or 7PM of the same day. Prioritize morning
        elif explicit_date:
          time_values.append({'datetime': processed_date.replace(hour=hour, minute=minute, second=0, microsecond=0), 'assumptions': [f'"{time}" is AM']})
          time_values.append({'datetime': processed_date.replace(hour=hour, minute=minute, second=0, microsecond=0) + datetime.timedelta(hours=12), 'assumptions': [f'"{time}" is PM']})
        # It's 5AM and I say 7 without a date, it may mean 7AM of today or 7PM of yesterday. Prioritize morning
        else:
          time_values.append({'datetime': processed_date.replace(hour=hour, minute=minute, second=0, microsecond=0), 'assumptions': [f'"{time}" is AM']})
          time_values.append({'datetime': processed_date.replace(hour=hour, minute=minute, second=0, microsecond=0) - datetime.timedelta(hours=12), 'assumptions': [f'"{time}" is PM']})

      for time_value in time_values:
        if cardinal_assumption:
          time_value['assumptions'].insert(0, cardinal_assumption)
        if date_assumption:
          time_value['assumptions'].insert(0, date_assumption)

      if len(time_values):
        results_data[k].append({'time': time, 'values': time_values})
      # Couldn't find any possible value for time (shouldn't happen); log and continue
      else:
        logging.error('No possible value found for time "%s"! Original text: "%s"', time, message)

  if len(results_data['time']) > 0:
    return (parsed_date, results_data['time'])

  # We're desperate for a time.
  if len(results_data['cardinal']) > 0:
    return (parsed_date, results_data['cardinal'])

  #if parsed_date:
  #  return (None, [{'time': parsed_date, 'values': []}])

  # Okay, I give up.
  return (parsed_date, [])
