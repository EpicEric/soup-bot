import asyncio
import datetime
import dateutil.tz
import discord
import logging
import random
import signal
import traceback

import db
import env
import nlp

def truncate_text(text, truncate_at):
  if len(text) <= truncate_at:
    return text
  return f'{text[:truncate_at-3]}...'

def run():
  discord.utils.setup_logging()

  intents = discord.Intents.default()
  intents.message_content = True
  intents.members = True

  client = discord.Client(intents=intents)

  dinkdonk_cache = {}
  dinkdonk_cache_limit = datetime.timedelta(minutes=30)

  @client.event
  async def on_ready():
    logging.info(f'{client.user} is active')

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
          await message.reply(f'Your timezone has been set to `{content}`. If this is correct, then your local time, **{local_time}**, should be the same as <t:{int(time_now.timestamp())}>.', mention_author=False)
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
          processed_results = nlp.process_time_message(truncate_text(content, 280), local_datetime)
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
        server_id = message.guild.id
        # Ensure that the command hasn't been used recently
        if server_id in dinkdonk_cache:
          next_dinkdonk = dinkdonk_cache[server_id]
          if next_dinkdonk > message.created_at:
            await message.reply(f'$dinkdonk is on cooldown! You\'ll get to use it again <t:{int(next_dinkdonk.timestamp())}:R>.', mention_author=False)
            return
        next_dd_timestamp = message.created_at + dinkdonk_cache_limit
        dinkdonk_cache[server_id] = next_dd_timestamp
        # Pick a random non-bot channel member
        channel_members = [m for m in client.get_channel(message.channel.id).members if not m.bot]
        random.seed(message.id + int(message.created_at.timestamp()))
        picked_member = random.sample(channel_members, 1)[0]
        # Persist increased count
        dd_count = db.save_dinkdonk_for_user(picked_member.id, server_id)
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
            'name': f'The bell has tolled for thee {dd_count} {"times" if dd_count > 1 else "time"}.',
            'inline': False,
            'value': f'*(command will be available again <t:{int(next_dd_timestamp.timestamp())}:R>)*',
          }],
        }
        await message.reply(None, embed=discord.Embed.from_dict(embed), mention_author=False)
        if (server_id, picked_member.id, dd_count) == (1088975500476698724, 98806161674862592, 10):
          await client.get_channel(message.channel.id).send('<@98806161674862592> I gave you 10 dinkdonks... can I earn my freedom now?')
      elif content == 'leaderboard':
        dd_list = sorted(db.get_dinkdonks_for_server(message.guild.id), key=lambda v: v[1], reverse=True)
        if len(dd_list) == 0:
          await message.reply('I couldn\'t find any $dinkdonk data for this server! Has this command been executed here before...?', embed=discord.Embed.from_dict(embed), mention_author=False)
        winners = {}
        winners_keys = ['1st place', '2nd place', '3rd place']
        # Build winners placements
        current_winners_keys = winners_keys.copy()
        current_key = current_winners_keys.pop(0)
        current_score = 0
        for dd in dd_list:
          if not current_score:
            current_score = dd[1]
          elif dd[1] < current_score:
            try:
              current_key = current_winners_keys.pop(0)
              current_score = dd[1]
            except IndexError:
              break
          current_winners = winners.get(current_key, (current_score, []))
          current_winners[1].append(dd[0])
          winners[current_key] = current_winners
        # Render winners placements
        fields = []
        for k in winners_keys:
          if k not in winners:
            break
          num_winners = len(winners[k][1])
          if num_winners > 5:
            value = ', '.join(f'<@{winner}>' for winner in winners[k][1][:4]) + f', and {num_winners - 4} others'
          elif num_winners > 2:
            value = ', '.join(f'<@{winner}>' for winner in winners[k][1][:-1]) + f', and <@{winners[k][1][-1]}>'
          else:
            value = ' and '.join(f'<@{winner}>' for winner in winners[k][1])
          fields.append({
            'name': f'{k} - {winners[k][0]} {"dinkdonks" if winners[k][0] > 1 else "dinkdonk"}',
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
      else:
        await message.reply('I don\'t understand that command! Use `$dinkdonk` to summon the evil, or `$dinkdonk leaderboard` to see who has the best RNG.', mention_author=False)

    # :goombaping:
    elif any(mention.id == client.user.id for mention in message.mentions):
      await message.reply('<:goombaping:1102105208760320000>')

  def on_exit(signum, frame):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(client.close)

  signal.signal(signal.SIGINT, on_exit)
  signal.signal(signal.SIGTERM, on_exit)

  client.run(env.DISCORD_TOKEN)
