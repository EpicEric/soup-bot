import datetime
import logging
from wit import Wit

import env

wit = None

ENT_DATETIME_KEY = 'wit$datetime:datetime'
ENT_GRAIN_DATE = ['day']
ENT_GRAIN_TIME = ['hour', 'minute', 'second']
ENT_GRAIN_VALID = [*ENT_GRAIN_DATE, *ENT_GRAIN_TIME]


class ProcessTimeMessageException(ValueError):
  pass


def init():
  global wit
  wit = Wit(env.WIT_TOKEN)

def _datetime_to_timestamp(dt):
  return int(dt.timestamp())

def _string_to_datetime(string):
  return datetime.datetime.fromisoformat(string)

def process_time_message(message, local_datetime_with_tz: datetime.datetime):
  if not wit:
    raise ValueError('NLP not initialized!')

  tz = local_datetime_with_tz.tzinfo

  doc = wit.message(message, context={'reference_time': local_datetime_with_tz.isoformat()})

  if not doc or 'entities' not in doc:
    logging.error('API returned unknown result: %s', doc)
    raise ProcessTimeMessageException('The API has returned an error! Please try again later.')

  try:
    if ENT_DATETIME_KEY not in doc['entities']:
      return []

    data_to_process = []
    for ent in doc['entities'][ENT_DATETIME_KEY]:
      body = ent['body']
      if ent['type'] == 'interval':
        is_interval = True
        # Interval may be missing start or end; convert to single value
        if 'from' not in ent:
          grain = ent['to']['grain']
          is_interval = False
          values = [v['to'] for v in ent['values']]
        elif 'to' not in ent:
          grain = ent['from']['grain']
          is_interval = False
          values = [v['from'] for v in ent['values']]
        else:
          grain = ent['from']['grain']
          values = ent['values']
      else:
        grain = ent['grain']
        is_interval = False
        values = ent['values']
      if grain in ENT_GRAIN_VALID:
        data_to_process.append((body, grain, is_interval, values))

    # Convert times
    results_data = []
    for (time_body, grain, is_interval, ent_values) in data_to_process:
      #time_body = ent['body']
      values = []
      exclusive_timedelta = datetime.timedelta(days=1 if grain == 'day' else 0, hours=1 if grain == 'hour' else 0, minutes=1 if grain == 'minute' else 0, seconds=1 if grain == 'second' else 0)
      #is_interval = ent['type'] == 'interval'

      # If it's a date
      if grain in ENT_GRAIN_DATE:
        hour = local_datetime_with_tz.hour
        minute = local_datetime_with_tz.minute
        second = local_datetime_with_tz.second
        # Format with date and time
        timestamp_suffix = ':D'
        for value in ent_values:
          if is_interval:
            date_value_from = _string_to_datetime(value['from']['value']).replace(hour=hour, minute=minute, second=second, tzinfo=tz)
            date_value_to = _string_to_datetime(value['to']['value']).replace(hour=hour, minute=minute, second=second, tzinfo=tz)
            values.append(f'<t:{_datetime_to_timestamp(date_value_from)}{timestamp_suffix}> to <t:{_datetime_to_timestamp(date_value_to - exclusive_timedelta)}{timestamp_suffix}>')
          else:
            date_value = _string_to_datetime(value['value']).replace(hour=hour, minute=minute, second=second, tzinfo=tz)
            values.append(f'<t:{_datetime_to_timestamp(date_value)}{timestamp_suffix}>')

      # If it's a time
      else:
        # Format with date and time by default
        timestamp_suffix = ':f'
        # Check which timestamp suffix should be used
        time_duplicates = set()
        values_to_save = []
        for value in ent_values:
          if is_interval:
            datetime_from = datetime.datetime.fromisoformat(value['from']['value'])
            datetime_to = datetime.datetime.fromisoformat(value['to']['value'])
            time_interval = (datetime_from.time(), datetime_to.time())
            if time_interval in time_duplicates:
              # If there are multiple possibilities for hours, format as hour instead of date+hour (to remove unnecessary ambiguity)
              timestamp_suffix = ':t'
            else:
              time_duplicates.add(time_interval)
              values_to_save.append((datetime_from, datetime_to))
          else:
            datetime_value = datetime.datetime.fromisoformat(value['value'])
            time_value = datetime_value.time()
            if time_value in time_duplicates:
              # If there are multiple possibilities for hours, format as hour instead of date+hour (to remove unnecessary ambiguity)
              timestamp_suffix = ':t'
            else:
              time_duplicates.add(time_value)
              values_to_save.append(datetime_value)
        for value in values_to_save:
          if is_interval:
            values.append(f'<t:{_datetime_to_timestamp(value[0].replace(tzinfo=tz))}{timestamp_suffix}> to <t:{_datetime_to_timestamp(value[1].replace(tzinfo=tz) - exclusive_timedelta)}{timestamp_suffix}>')
          else:
            values.append(f'<t:{_datetime_to_timestamp(value.replace(tzinfo=tz))}{timestamp_suffix}>')

      if len(values) == 0:
        logging.error('Couldn\'t find any values for body "%s"!', time_body)
        continue
      results_data.append((time_body, values))

    return results_data
  except ProcessTimeMessageException:
    raise
  except Exception as e:
    raise ValueError(f'Error raised when processing doc "{doc}"') from e

