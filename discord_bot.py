import asyncio
import datetime
import dateutil.rrule
import dateutil.tz
import discord
import json
import logging as pyLogging
import random
import signal
import traceback

import db
import env
import nlp
import utils

DINKDONK_CACHE_LIMIT = datetime.timedelta(minutes=30)
DINKDONK_THRESHOLD = 80

EMOTE_DINKDONK = '<a:DinkDonk:1102105207439110174>'
EMOTE_GOOMBAPING = '<:goombaping:1102105208760320000>'


def truncate_text(text, truncate_at):
  if len(text) <= truncate_at:
    return text
  return f'{text[:truncate_at-3]}...'

def run():
  discord.utils.setup_logging()
  logging = pyLogging.getLogger('soupbot')

  intents = discord.Intents.default()
  intents.guilds = True
  intents.message_content = True
  intents.members = True
  intents.guild_messages = True

  client = discord.Client(intents=intents)

  @client.event
  async def on_ready():
    logging.info(f'{client.user} is active and listening to {len(client.guilds)} server(s)')
    for guild in client.guilds:
      logging.info(f' - {guild.name} (id: {guild.id})')

  @client.event
  async def on_guild_join(guild: discord.Guild):
    logging.info(f'Joined guild "{guild.name}" (id: {guild.id})')

  @client.event
  async def on_guild_remove(guild: discord.Guild):
    logging.info(f'Left guild "{guild.name}" (id: {guild.id})')

  @client.event
  async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == client.user.id:
      return
    if str(payload.emoji) == EMOTE_GOOMBAPING:
      logging.info(f'User "{payload.user_id}" reacted to message "{payload.message_id}" in channel "{payload.channel_id}" with goombaping')

  @client.event
  async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.user_id == client.user.id:
      return
    if str(payload.emoji) == EMOTE_GOOMBAPING:
      logging.info(f'User "{payload.user_id}" has removed the goombaping from message "{payload.message_id}" in channel "{payload.channel_id}"')

  @client.event
  async def on_message(message: discord.Message):
    if message.author == client.user:
      return

    command = None
    split_message = message.content.split(maxsplit=1)
    if len(split_message) > 0 and split_message[0][0] == '$':
      command = split_message[0]

    # Identify local timezone and then save it
    if command == '$settimezone':
      try:
        content = message.content[12:].strip()
        tz = None
        if not content:
          tz = db.get_timezone_for_user_id(message.author.id)
          if tz:
            time_now = datetime.datetime.now(dateutil.tz.tzutc())
            local_time = datetime.datetime.fromtimestamp(time_now.timestamp(), tz=dateutil.tz.gettz(tz)).strftime('%Y-%m-%d at %H:%M (%Z)')
            await message.reply(f'Your timezone is currently set to `{tz}`. If this is correct, then your local time should be **{local_time}**.\n\nYou can change it with **$settimezone Your/Timezone**, or remove it with **$settimezone clear**.\n\nFor a list of valid timezones, check out: https://nodatime.org/TimeZones', mention_author=False)
            return
          else:
            await message.reply(f'You haven\'t selected a timezone yet. You can choose one with **$settimezone Your/Timezone**\n\nFor a list of valid timezones, check out: https://nodatime.org/TimeZones', mention_author=False, suppress_embeds=True)
            return
        if content == 'help':
          await message.reply(f'You can use this command to select a timezone.\n- **$settimezone Your/Timezone** to choose a timezone; a list of valid timezones can be found here: https://nodatime.org/TimeZones\n- **$settimezone** displays your current timezone (if set)\n- **$settimezone clear** deletes your current timezone', mention_author=False, suppress_embeds=True)
          return
        if content != 'clear':
          tz = dateutil.tz.gettz(content)
          if not tz:
            await message.reply(f'Unknown timezone `{truncate_text(content, 70)}`. Check this list for valid time zone IDs: https://nodatime.org/TimeZones', mention_author=False, suppress_embeds=True)
            return
        db.set_timezone_for_user_id(message.author.id, content if tz else None, timestamp=message.created_at)
        if tz:
          time_now = datetime.datetime.now(dateutil.tz.tzutc())
          local_time = datetime.datetime.fromtimestamp(time_now.timestamp(), tz=tz).strftime('%Y-%m-%d at %H:%M (%Z)')
          await message.reply(f'Your timezone has been set to `{content}`. If this is correct, then your local time, **{local_time}**, should be the same as <t:{utils.datetime_to_timestamp(time_now)}>.', mention_author=False)
        else:
          await message.reply(f'Your timezone has been removed.', mention_author=False)
      except Exception as e:
        logging.error('Exception raised in $settimezone command')
        logging.exception(e)
        traceback.print_exc()
        await message.reply('An unknown internal error has occurred.', mention_author=False)

    # Smartly translate local time to Discord timestamp
    elif command == '$time':
      if message.content.strip().lower().split() == ['$time', 'is', 'soup']:
        await message.reply('Yeah')
        return
      elif message.content.startswith('$timezone'):
        await message.reply('Did you mean to use $settimezone instead?', mention_author=False)
        return
      try:
        reply_to = message
        reply = 'You haven\'t selected a timezone yet! Use the command **$settimezone timezone** to do so, and let others translate your local time as well.'
        content = message.content[5:].strip()
        message_author = message.author
        timestamp = message.created_at

        if content == 'help':
          await message.reply(f'You can use this command to infer the local time from someone\'s message, if they\'ve selected a timezone with $settimezone.\n\nSimply add **$time** to the start of your message, or reply to an existing message with **$time**, to have the mentioned time(s) translated to everyone\'s local time.', mention_author=False)
          return

        # If it's a reply to another message, use that instead
        if message.reference and isinstance(message.reference.resolved, discord.Message):
          replied_message = message.reference.resolved
          if replied_message.author.bot or not(hasattr(replied_message.author, 'id')):
            await message.reply(f'Can\'t process messages by bots or unknown users!', mention_author=False)
            return
          content = replied_message.content
          if content.startswith('$time'):
            content = content[5:]
          content = content.strip()
          timestamp = replied_message.created_at
          reply_to = replied_message
          if replied_message.author.id != message_author.id:
            reply = f'{replied_message.author.display_name} hasn\'t selected a timezone yet! Instruct them to use the command **$settimezone timezone** if you wish to translate their local time.'
            message_author = replied_message.author

        if not content:
          await reply_to.reply('Cannot get time from empty message! Make sure that you\'re replying to the message you want to read time from.', mention_author=False)
          return

        # Find timezone for message author
        tz_name = db.get_timezone_for_user_id(message_author.id)
        if not tz_name:
          await message.reply(reply, mention_author=False)
          return
        tz = dateutil.tz.gettz(tz_name)
        local_datetime = datetime.datetime.fromtimestamp(timestamp.timestamp(), tz=tz)

        # Process the message with NLP model
        try:
          processed_results = await nlp.process_time_message(truncate_text(content, 280), local_datetime)
        except nlp.ProcessTimeMessageException as e:
          logging.error('Failed to parse message "%s" in $time command', content)
          logging.exception(e)
          traceback.print_exc()
          await reply_to.reply(str(e), mention_author=False)
          return
        if len(processed_results) == 0:
          await reply_to.reply('Couldn\'t find any time in this message! Make sure to reply to a message containing time, or include your local time in your message.', mention_author=False)
          return
        # Pretty format data
        embed_fields = []
        for (time, values) in processed_results:
          field_value = []
          line_prefix = ''
          if len(values) > 1:
            line_prefix = '- '
            field_value.append('Could be one of:')
          for value in values:
            field_value.append(f'{line_prefix}{value}')
          embed_fields.append({
            'name': f'For "{time}"',
            'inline': False,
            'value': '\n'.join(field_value)
          })
        embed = {
          'color': 4321431,
          'title': f'$time for `{tz_name}`',
          'author': {
            'name': message_author.display_name,
            'icon_url': message_author.display_avatar.url,
          },
          'footer': {
            'text': '$time is soup',
            'icon_url': client.user.avatar.url,
          },
          'timestamp': datetime.datetime.utcnow().isoformat(),
          'description': f'> {truncate_text(content, 200)}',
          'fields': embed_fields,
        }
        await reply_to.reply(None, embed=discord.Embed.from_dict(embed), mention_author=False)
      except Exception as e:
        logging.error('Exception raised in $time command')
        logging.exception(e)
        traceback.print_exc()
        await message.reply('An unknown internal error has occurred.', mention_author=False)

    # DinkDonks someone without pinging them
    elif command == '$dinkdonk':
      content = message.content[9:].strip()

      if content == 'help':
        await message.reply(f'Ask for whom the dinkdonk tolls.\n- **$dinkdonk** brings the bell\'s wrath upon this channel.\n- **$dinkdonk leaderboard** shows the people that donk the most dinks.\n- **$dinkdonk reset** is a special command, only available when someone is way ahead of the others...\n- **$mydinkdonks** displays your personal stats.', mention_author=False)
        return

      if not content:
        try:
          server_id = message.guild.id
          # Ensure that the command hasn't been used recently
          next_dinkdonk = db.get_dd_cache(server_id)
          if next_dinkdonk is not None and next_dinkdonk.timestamp() > message.created_at.timestamp():
            await message.reply(f'$dinkdonk is on cooldown! You\'ll get to use it again <t:{utils.datetime_to_timestamp(next_dinkdonk)}:R>.', mention_author=False)
            return
          next_dd_timestamp = message.created_at + DINKDONK_CACHE_LIMIT
          channel_members = [m for m in client.get_channel(message.channel.id).members if not m.bot]
          if len(channel_members) < 1:
            await message.reply(f'$dinkdonk is not available here! Use the command in a valid channel.', mention_author=False)
            return
          elif len(channel_members) == 1:
            await message.reply(f'$dinkdonk is only available when there are at least two users in the channel.', mention_author=False)
            return
          db.set_dd_cache(server_id, next_dd_timestamp)
          # Pick a random non-bot channel member
          random.seed(message.id + utils.datetime_to_timestamp(message.created_at))
          picked_member = random.sample(channel_members, 1)[0]
          could_reset_dds = db.check_if_has_reset_privilege(picked_member.id, server_id, None)
          # Persist increased count
          dd_count = db.save_dinkdonk_for_user(picked_member.id, server_id, from_user_id=message.author.id)
          value_prefix = ''
          if dd_count >= DINKDONK_THRESHOLD:
            value_prefix = 'Too many dinkdonks!!! Now *anybody* can use `$dinkdonk reset`.\n'
          elif could_reset_dds:
            value_prefix = 'This user can still use `$dinkdonk reset`. Just saying...\n'
          elif db.check_if_has_reset_privilege(picked_member.id, server_id, None):
            value_prefix = 'This user can now use `$dinkdonk reset`, and reset all dinkdonks in this server while they\'re ahead in first place!\n'
          snarky_count_comment = ''
          if dd_count == 69:
            snarky_count_comment = ' (nice)'
          should_alert = db.get_dinkdonk_should_alert(picked_member.id, server_id)
          embed = {
            'color': 4321431,
            'title': '$dinkdonk',
            'author': {
              'name': picked_member.display_name,
              'icon_url': picked_member.display_avatar.url,
            },
            'footer': {
              'text': 'Ask not for whom the $dinkdonk tolls...',
              'icon_url': client.user.avatar.url,
            },
            'timestamp': datetime.datetime.utcnow().isoformat(),
            'description': f'{EMOTE_DINKDONK} <@{picked_member.id}>{" (haha get rekt)" if picked_member.id == message.author.id else ""}',
            'fields': [{
              'name': f'The bell has tolled for thee {dd_count} {"times" if dd_count > 1 else "time"}{snarky_count_comment}.',
              'inline': False,
              'value': f'{value_prefix}*(command will be available again <t:{utils.datetime_to_timestamp(next_dd_timestamp)}:R>)*',
            }],
          }
          await message.reply(f'{EMOTE_DINKDONK} <@{picked_member.id}>' if should_alert else None, embed=discord.Embed.from_dict(embed), mention_author=False)
        except Exception as e:
          logging.error('Exception raised in $dinkdonk command')
          logging.exception(e)
          traceback.print_exc()
          await message.reply('An unknown internal error has occurred.', mention_author=False)
      elif content == 'leaderboard':
        try:
          dd_list = db.get_dinkdonks_for_server(message.guild.id)
          if len(dd_list) == 0:
            await message.reply('I couldn\'t find any $dinkdonk data for this server! Has this command been executed here before...?', embed=discord.Embed.from_dict(embed), mention_author=False)
          ranked_dd_list = utils.rank_dinkdonks(dd_list, cut_off_at_length=3)
          # Render winners placements
          fields = []
          for (i, dd) in enumerate(ranked_dd_list):
            num_winners = len(dd[1])
            if num_winners > 5:
              value = ', '.join(f'<@{winner}>' for winner in dd[1][:4]) + f', and {num_winners - 4} others'
            elif num_winners > 2:
              value = ', '.join(f'<@{winner}>' for winner in dd[1][:-1]) + f', and <@{dd[1][-1]}>'
            else:
              value = ' and '.join(f'<@{winner}>' for winner in dd[1])
            fields.append({
              'name': f'{utils.get_ordinal(i + 1)} place - {dd[0]} {"dinkdonks" if dd[0] > 1 else "dinkdonk"}',
              'inline': False,
              'value': value,
            })
          for (i, field) in enumerate(fields):
            field['name'] += f' {EMOTE_DINKDONK}' * (len(fields) - i)
          embed = {
            'color': 4321431,
            'title': '$dinkdonk leaderboard',
            'footer': {
              'text': 'Ask not for whom the $dinkdonk tolls...',
              'icon_url': client.user.avatar.url,
            },
            'timestamp': datetime.datetime.utcnow().isoformat(),
            'fields': fields,
          }
          await message.reply(None, embed=discord.Embed.from_dict(embed), mention_author=False)
        except Exception as e:
          logging.error('Exception raised in $dinkdonk leaderboard command')
          logging.exception(e)
          traceback.print_exc()
          await message.reply('An unknown internal error has occurred.', mention_author=False)
      elif content == 'alert':
        try:
          db.toggle_dinkdonk_alerts(message.author.id, message.guild.id)
          should_alert = db.get_dinkdonk_should_alert(message.author.id, message.guild.id)
          if should_alert:
            await message.reply('You will be alerted when you receive a $dinkdonk in this server.', mention_author=True)
          else:
            await message.reply('You will no longer be alerted when you receive a $dinkdonk in this server.', mention_author=False)
        except Exception as e:
          logging.error('Exception raised in $dinkdonk alert command')
          logging.exception(e)
          traceback.print_exc()
          await message.reply('An unknown internal error has occurred.', mention_author=False)
      elif content == 'reset':
        try:
          user_id = message.author.id
          server_id = message.guild.id
          can_reset_dds = db.check_if_has_reset_privilege(user_id, server_id, DINKDONK_THRESHOLD)
          if can_reset_dds:
            timestamp = message.created_at
            db.set_dd_cache(server_id, None)
            all_dinkdonks_at_winner = db.get_cross_dinkdonks_at_user(user_id, server_id)
            dd_list = db.get_dinkdonks_for_server(server_id)
            ranked_dd_list = utils.rank_dinkdonks(dd_list)
            # Render winners' placements
            fields = []
            MAX_FIELDS = 24
            for (i, (dd_count, dd_users)) in enumerate(ranked_dd_list[:MAX_FIELDS]):
              if len(dd_users) > 2:
                value = ', '.join(f'<@{winner}>' for winner in dd_users[:-1]) + f', and <@{dd_users[-1]}>'
              else:
                value = ' and '.join(f'<@{winner}>' for winner in dd_users)
              fields.append({
                'name': f'{utils.get_ordinal(i + 1)} place - {dd_count} {"dinkdonks" if dd_count > 1 else "dinkdonk"}',
                'inline': False,
                'value': value,
              })
            sum_others = sum(len(users) for (_, users) in ranked_dd_list[MAX_FIELDS:])
            if sum_others:
              fields.append({
                'name': f'...and at the bottom...',
                'inline': False,
                'value': f'{sum_others} {"others" if sum_others > 1 else "other"} ranked lower than {utils.get_ordinal(MAX_FIELDS)} place',
              })
            embed = {
              'color': 4321431,
              'title': 'Final $dinkdonk results',
              'footer': {
                'text': 'Ask not for whom the $dinkdonk tolls...',
                'icon_url': client.user.avatar.url,
              },
              'timestamp': datetime.datetime.utcnow().isoformat(),
              'fields': fields,
            }
            if len(all_dinkdonks_at_winner) > 0:
              max_dinkdonks_at_winner = max(all_dinkdonks_at_winner, key=lambda x: x[1])
              scoreboard_message = await message.reply(f'$dinkdonks reset! <@{user_id}> has been awarded one dinkdonk as well. {EMOTE_DINKDONK} (you can blame <@{max_dinkdonks_at_winner[0]}> for {max_dinkdonks_at_winner[1]} of those dinkdonks...)\n\nHere are the final results prior to reset:', embed=discord.Embed.from_dict(embed))
            else:
              scoreboard_message = await message.reply(f'$dinkdonks reset! <@{user_id}> has been awarded one dinkdonk as well. {EMOTE_DINKDONK}\n\nHere are the final results prior to reset:', embed=discord.Embed.from_dict(embed))
            db.clear_server_dinkdonks(server_id, timestamp=timestamp)
            db.save_dinkdonk_for_user(user_id, server_id, timestamp=timestamp)
            this_member = [m for m in client.get_channel(scoreboard_message.channel.id).members if m.id == client.user.id][0]
            if scoreboard_message.channel.permissions_for(this_member).manage_messages:
              try:
                await scoreboard_message.pin()
              except Exception as e:
                logging.warning('Failed to pin leaderboard message to %s', scoreboard_message.channel.name)
                logging.exception(e)
          else:
            await message.reply(f'Oops, can\'t do that! Resetting the count is a privilege of the almighty reigning Dinkdonk Champion, who has conquered the leaderboard with {db.DINKDONK_RESET_PRIVILEGE_MINIMUM} dinkdonks. You\'re just a humble serf without enough dinkdonks to play with the big bells. Time to hustle and earn those sweet jingles!', mention_author=False)
        except Exception as e:
          logging.error('Exception raised in $dinkdonk reset command')
          logging.exception(e)
          traceback.print_exc()
          await message.reply('An unknown internal error has occurred.', mention_author=False)
      else:
        await message.reply('I don\'t understand that command! Use `$dinkdonk` to summon the bell or `$dinkdonk leaderboard` to see who has been punished the most by the RNG.', mention_author=False)

    elif command == '$mydinkdonks':
      try:
        this_user_id = str(message.author.id)
        (count, lifetime_count) = db.get_all_dinkdonks_for_user(message.author.id, message.guild.id)
        if count == 0:
          if lifetime_count == 0:
            await message.reply('You have no dinkdonks! I\'m clearly not doing my job...', mention_author=False)
          else:
            await message.reply(f'You have no dinkdonks right now, but {lifetime_count} from past resets.', mention_author=False)
        else:
          dd_list_place = len(utils.rank_dinkdonks(db.get_dinkdonks_for_server(message.guild.id), cut_off_at_user_id=this_user_id))
          if lifetime_count == count:
            await message.reply(f'You have {count} {"dinkdonks" if count > 1 else "dinkdonk"} in total. You are in {utils.get_ordinal(dd_list_place)} place.', mention_author=False)
          else:
            await message.reply(f'You have {count} {"dinkdonks" if count > 1 else "dinkdonk"} right now, and {lifetime_count} when including past resets. You are currently in {utils.get_ordinal(dd_list_place)} place.', mention_author=False)
      except Exception as e:
        logging.error('Exception raised in $mydinkdonks command')
        logging.exception(e)
        traceback.print_exc()
        await message.reply('An unknown internal error has occurred.', mention_author=False)

    elif command in ('$unavailable', '$available'):
      reply_to = message
      server_id = message.guild.id
      messages_to_process: list = [message]
      # If it's a reply to another message, use that first
      if message.reference:
        new_message = message.reference.resolved
        if isinstance(new_message, discord.Message):
          messages_to_process.insert(0, new_message)
      for message in messages_to_process:
        author = message.author
        user_id = author.id
        timestamp = message.created_at
        tz_name = db.get_timezone_for_user_id(author.id)
        tz = dateutil.tz.gettz(tz_name if tz_name else "America/Los_Angeles")
        local_datetime = datetime.datetime.fromtimestamp(timestamp.timestamp(), tz=tz)
        content = message.content
        if content[0] == '$':
          content = content.split(" ", 1)[1].strip()
        if not content:
          continue
        try:
          processed_results = await nlp.process_time_message(truncate_text(content, 280), local_datetime, nlp.ENT_GRAIN_DATE)
        except nlp.ProcessTimeMessageException as e:
          logging.error('Failed to parse message "%s" in %s command', content, command)
          logging.exception(e)
          traceback.print_exc()
          continue
        if len(processed_results) == 0 or len(processed_results) > 1:
          continue
        # Match found, add to DB
        if len(message.mentions) > 0 and message.mentions[0].id != client.user.id:
          user_id = message.mentions[0].id
        if len(processed_results) == 0 or len(processed_results[0][1]) == 0:
          continue
        timestamp = processed_results[0][1][0]
        timestamp_unix = timestamp.split(":", 2)[1]
        on_date = datetime.datetime.fromtimestamp(int(timestamp_unix), tz=tz).astimezone(dateutil.tz.gettz("America/Anchorage")).date()
        is_available = command == "$available"
        db.set_availability_for_user(server_id, user_id, on_date, is_available, content)
        await message.reply(f'Marked {"you" if reply_to.author.id == user_id else author.display_name} as {"available" if is_available else "unavailable"} on {timestamp}.', mention_author=False)
        return
      await reply_to.reply('Unable to find a date in this message! Make sure to keep it unambiguous and concise, and don\'t use times.', mention_author=False)

    elif command == '$whoisavailable':
      server_id = message.guild.id
      author = message.author
      content = message.content[15:].strip()
      timestamp = message.created_at
      tz_name = db.get_timezone_for_user_id(author.id)
      tz = dateutil.tz.gettz(tz_name if tz_name else "America/Anchorage")
      local_datetime = datetime.datetime.fromtimestamp(timestamp.timestamp(), tz=tz)
      try:
        processed_results = await nlp.process_time_message(truncate_text(content, 280), local_datetime, nlp.ENT_GRAIN_DATE)
      except nlp.ProcessTimeMessageException as e:
        logging.error('Failed to parse message "%s" in $whoisavailable command', content)
        logging.exception(e)
        traceback.print_exc()
        await message.reply(str(e), mention_author=False)
        return
      if len(processed_results) == 0 or len(processed_results) > 1:
        await message.reply('Unable to find a date in this message! Make sure to keep it unambiguous and concise, and don\'t use times.', mention_author=False)
        return
      timestamp = processed_results[0][1][0]
      timestamp_unix = timestamp.split(":", 2)[1]
      on_date = datetime.datetime.fromtimestamp(int(timestamp_unix), tz=tz).astimezone(dateutil.tz.gettz("America/Anchorage")).date()
      availabilities = db.get_availabilities_for_date(server_id, on_date)
      available, unavailable = [], []
      if len(availabilities) == 0:
        await message.reply(f'No data for {timestamp} yet.', mention_author=False)
        return
      for (user_id, is_available, description) in availabilities:
        if is_available:
          available.append({
            "name": "",
            "inline": False,
            "value": f'<@{user_id}> {description}',
          })
        else:
          unavailable.append({
            "name": "",
            "inline": False,
            "value": f'<@{user_id}> {description}',
          })
      embeds = []
      if len(available) > 0:
        embeds.append(discord.Embed.from_dict({
          'color': 4845668,
          'title': '$available',
          'fields': available,
        }))
      if len(unavailable) > 0:
        embeds.append(discord.Embed.from_dict( {
          'color': 15747401,
          'title': '$unavailable',
          'fields': unavailable,
        }))
      await message.reply(f'Here is the data I have for {timestamp} so far:', embeds=embeds, mention_author=False)

    # Custom command defined by SOUPBOT_CUSTOM_COMMAND envvar (invoked with $command)
    elif command in env.CUSTOM:
        await message.reply(env.CUSTOM[command], mention_author=False)

    # :goombaping:
    elif any(mention.id == client.user.id for mention in message.mentions):
      await message.reply(EMOTE_GOOMBAPING)

  def on_exit(signum, frame):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(client.close)

  signal.signal(signal.SIGINT, on_exit)
  signal.signal(signal.SIGTERM, on_exit)

  client.run(env.DISCORD_TOKEN)
