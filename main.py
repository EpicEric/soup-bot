import db
import env
import nlp
import discord_bot

def main():
  env.init_env()
  nlp.init()
  db.init()
  discord_bot.run()

if __name__ == '__main__':
  main()
