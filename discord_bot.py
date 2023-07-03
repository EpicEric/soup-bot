import asyncio
import datetime
import dateutil.tz
import discord
import logging as pyLogging
import random
import signal
import traceback

import db
import env
import nlp
import utils

DINKDONK_CACHE_LIMIT = datetime.timedelta(minutes=30)


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
  async def on_message(message: discord.Message):
    if message.author == client.user:
      return

    # Identify local timezone and then save it
    if message.content.startswith('$settimezone'):
      try:
        content = message.content[12:].strip()
        tz = None
        if not content:
          tz = db.get_timezone_for_user_id(message.author.id)
          if tz:
            await message.reply(f'Your timezone is currently set to `{tz}`. You can change it with **$settimezone Your/Timezone**, or remove it with **$settimezone clear**.', mention_author=False)
            return
          else:
            await message.reply(f'You haven\'t selected a timezone yet. You can choose one with **$settimezone Your/Timezone**\n\nFor a list of valid timezones, check out: https://nodatime.org/TimeZones', mention_author=False, suppress_embeds=True)
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
    elif message.content.startswith('$time'):
      if message.content.strip().lower() == '$time is soup':
        await message.reply('Yeah')
        return
      try:
        reply_to = message
        reply = 'You haven\'t selected a timezone yet! Use the command **$settimezone timezone** to do so, and let others translate your local time as well.'
        content = message.content[5:].strip()
        message_author = message.author
        timestamp = message.created_at

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
    elif message.content.startswith('$dinkdonk'):
      content = message.content[9:].strip()
      if not content:
        try:
          server_id = message.guild.id
          # Ensure that the command hasn't been used recently
          next_dinkdonk = db.get_dd_cache(server_id)
          if next_dinkdonk is not None and next_dinkdonk.timestamp() > message.created_at.timestamp():
            await message.reply(f'$dinkdonk is on cooldown! You\'ll get to use it again <t:{utils.datetime_to_timestamp(next_dinkdonk)}:R>.', mention_author=False)
            return
          next_dd_timestamp = message.created_at + DINKDONK_CACHE_LIMIT
          db.set_dd_cache(server_id, next_dd_timestamp)
          # Pick a random non-bot channel member
          channel_members = [m for m in client.get_channel(message.channel.id).members if not m.bot]
          random.seed(message.id + utils.datetime_to_timestamp(message.created_at))
          picked_member = random.sample(channel_members, 1)[0]
          could_reset_dds = db.check_if_has_reset_privilege(picked_member.id, server_id)
          # Persist increased count
          dd_count = db.save_dinkdonk_for_user(picked_member.id, server_id)
          value_prefix = ''
          if could_reset_dds:
            value_prefix = 'This user can still use `$dinkdonk reset`. Just saying...\n'
          elif db.check_if_has_reset_privilege(picked_member.id, server_id):
            value_prefix = 'This user can now use `$dinkdonk reset`, and reset all dinkdonks in this server while they\'re ahead in first place!\n'
          snarky_count_comment = ''
          if dd_count == 69:
            snarky_count_comment = ' (nice)'
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
            'description': f'<a:DinkDonk:1102105207439110174> <@{picked_member.id}>{" (haha get rekt)" if picked_member.id == message.author.id else ""}',
            'fields': [{
              'name': f'The bell has tolled for thee {dd_count} {"times" if dd_count > 1 else "time"}{snarky_count_comment}.',
              'inline': False,
              'value': f'{value_prefix}*(command will be available again <t:{utils.datetime_to_timestamp(next_dd_timestamp)}:R>)*',
            }],
          }
          await message.reply(None, embed=discord.Embed.from_dict(embed), mention_author=False)
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
            field['name'] += " <a:DinkDonk:1102105207439110174>" * (len(fields) - i)
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
      elif content == 'reset':
        try:
          user_id = message.author.id
          server_id = message.guild.id
          can_reset_dds = db.check_if_has_reset_privilege(user_id, server_id)
          if can_reset_dds:
            timestamp = message.created_at
            db.set_dd_cache(server_id, None)
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
            scoreboard_message = await message.reply(f'$dinkdonks reset! <@{user_id}> has been awarded one dinkdonk as well. <a:DinkDonk:1102105207439110174>\n\nHere are the final results prior to reset:', embed=discord.Embed.from_dict(embed))
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

    elif message.content.startswith('$mydinkdonks'):
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
        logging.error('Exception raised in $dinkdonk reset command')
        logging.exception(e)
        traceback.print_exc()
        await message.reply('An unknown internal error has occurred.', mention_author=False)

    # :goombaping:
    elif any(mention.id == client.user.id for mention in message.mentions):
      await message.reply('<:goombaping:1102105208760320000>')

  def on_exit(signum, frame):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(client.close)

  signal.signal(signal.SIGINT, on_exit)
  signal.signal(signal.SIGTERM, on_exit)

  client.run(env.DISCORD_TOKEN)
