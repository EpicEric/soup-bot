import aiohttp
import datetime
import json
import logging as pyLogging
import traceback

import env
import utils

logging = pyLogging.getLogger('soupbot.nlp')
wit = None

class Wit:
  def __init__(self, token: str):
    self.token = token

  async def message(self, msg: str, reference_time: datetime.datetime):
    params = {
      'v': '20230215',
      'q': msg[:280],
      'context': json.dumps({'reference_time': reference_time.replace(microsecond=0).isoformat()}), 
    }
    headers = {
      'Authorization': f'Bearer {self.token}',
      'Accept': 'application/json'
    }
    async with aiohttp.ClientSession() as session:
      async with session.get('https://api.wit.ai/message', params=params, headers=headers) as r:
        if r.status != 200:
          raise ValueError(f'Received HTTP status {r.status}')
        json_body = await r.json()
        if 'error' in json_body:
          raise ValueError(f'Received error in response: {r.dumps(json_body["error"])}')
        return json_body

ENT_DATETIME_KEY = 'wit$datetime:datetime'
ENT_GRAIN_DATE = {'day'}
ENT_GRAIN_TIME = {'hour', 'minute', 'second'}
ENT_GRAIN_DATETIME = ENT_GRAIN_DATE | ENT_GRAIN_TIME


class ProcessTimeMessageException(ValueError):
  pass


def init():
  global wit
  wit = Wit(env.WIT_TOKEN)

async def process_time_message(message, local_datetime_with_tz: datetime.datetime, valid_grains = None):
  if not wit:
    raise ValueError('NLP not initialized!')
  if not valid_grains:
    valid_grains = ENT_GRAIN_DATETIME
  elif type(valid_grains) is str:
    valid_grains = set([valid_grains])
  elif type(valid_grains) is not set:
    valid_grains = set(valid_grains)

  tz = local_datetime_with_tz.tzinfo

  try:
    doc = await wit.message(message, local_datetime_with_tz)
  except Exception as e:
    logging.error('WIT API error')
    logging.exception(e)
    traceback.print_exc()
    logging.error('API error')
    raise ProcessTimeMessageException('The API has returned an error! Please try again later.')

  if 'entities' not in doc:
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
      if grain in ENT_GRAIN_DATETIME:
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
            datetime_from = datetime.datetime.fromisoformat(value['from']['value']).replace(hour=hour, minute=minute, second=second)
            datetime_to = datetime.datetime.fromisoformat(value['to']['value']).replace(hour=hour, minute=minute, second=second)
            values.append(f'<t:{utils.datetime_to_timestamp(datetime_from)}{timestamp_suffix}> to <t:{utils.datetime_to_timestamp(datetime_to - exclusive_timedelta)}{timestamp_suffix}>')
          else:
            date_value = datetime.datetime.fromisoformat(value['value']).replace(hour=hour, minute=minute, second=second)
            values.append(f'<t:{utils.datetime_to_timestamp(date_value)}{timestamp_suffix}>')

      # If it's a time but we only care about days
      elif grain in ENT_GRAIN_TIME and 'day' in valid_grains and valid_grains.isdisjoint(ENT_GRAIN_TIME):
        timestamp_suffix = ':D'
        for value in ent_values:
          if is_interval:
            datetime_from = datetime.datetime.fromisoformat(value['from']['value'])
            datetime_to = datetime.datetime.fromisoformat(value['to']['value']) - datetime.timedelta(seconds=1)
            if datetime_from.date() == datetime_to.date():
              values.append(f'<t:{utils.datetime_to_timestamp(datetime_from)}{timestamp_suffix}>')
          else:
            date_value = datetime.datetime.fromisoformat(value['value'])
            values.append(f'<t:{utils.datetime_to_timestamp(date_value)}{timestamp_suffix}>')

      # If it's a time
      elif grain in ENT_GRAIN_TIME:
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
            # If there are multiple possibilities for hours, format as hour instead of date+hour (to remove unnecessary ambiguity)
            if time_interval in time_duplicates:
              timestamp_suffix = ':t'
            else:
              time_duplicates.add(time_interval)
              values_to_save.append((datetime_from, datetime_to))
          else:
            datetime_value = datetime.datetime.fromisoformat(value['value'])
            time_value = datetime_value.time()
            # If there are multiple possibilities for hours, format as hour instead of date+hour (to remove unnecessary ambiguity)
            if time_value in time_duplicates:
              timestamp_suffix = ':t'
            else:
              time_duplicates.add(time_value)
              values_to_save.append(datetime_value)
        for value in values_to_save:
          if is_interval:
            values.append(f'<t:{utils.datetime_to_timestamp(value[0])}{timestamp_suffix}> to <t:{utils.datetime_to_timestamp(value[1] - exclusive_timedelta)}{timestamp_suffix}>')
          else:
            values.append(f'<t:{utils.datetime_to_timestamp(value)}{timestamp_suffix}>')

      if len(values) == 0:
        logging.error('Couldn\'t find any values for body "%s"!', time_body)
        continue
      results_data.append((time_body, values))

    return results_data
  except ProcessTimeMessageException:
    raise
  except Exception as e:
    raise ValueError(f'Error raised when processing doc "{doc}"') from e
