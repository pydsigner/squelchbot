import json
import time

from irc.bot import Bot


class Ident(object):
    name = 'Spam Squelch Bot'

    def __init__(self, conf):
        self.serv = 'bot'
        self.host = conf.get('irc_server', 'irc.freenode.net')
        self.port = conf.get('irc_port', 6667)
        self.ident = conf.get('username', 'OpenSquelchBot')
        self.nick = conf.get('nick', self.ident)
        self.server_pass = conf.get('server_password', None)
        self.nickserv_pass = conf.get('nickserv_password', None)
        self.joins = conf.get('channels', [])


class Commands(object):
    def __init__(self, bot, conf):
        self.ident = bot.ident
        self.conn = bot.conn

        self.admins = set(conf.get('admin_users', []))

        self.default_score = conf.get('default_score', -0.5)
        self.message_score = conf.get('message_score', -0.7)
        self.minimum_score = conf.get('minimum_score', -100)
        self.removal_score = conf.get('removal_score', 0)

        self.known_users = set()
        self.user_scores = {}

        self.unaddr_funcs = {
            '!reset_names': self.reset_names,
            '!count_names': self.show_names,
            '!reset_scores': self.reset_scores,
            '!show_scores': self.show_scores,
            '!add_admin': self.add_admin,
            '!join_channel': self.join_channel,
            '!leave_channel': self.leave_channel
        }

        self.all_privmsg_funcs = [self.privmsg]

        self.other_join_funcs = [self.user_joined]
        self.on_name_list = [self.handle_name_list]

    def handle_name_list(self, nicks, channel):
        self.known_users |= set(n.strip('@').strip('+') for n in nicks)

    def user_joined(self, meta):
        self.known_users.add(meta['nick'])

    def privmsg(self, tokens, meta):
        user = meta['nick']
        chan = meta['channel']

        self.user_scores.setdefault(user, self.default_score)

        self.user_scores[user] += self.score_message(tokens)

        score = self.user_scores[user]

        if score >= self.removal_score:
            # Don't attempt to kick in PM, and don't kick admins either
            if user not in self.admins | {chan}:
                self.remove_user(user, meta['host'], chan, score)
        else:
            self.user_scores[user] = max(self.minimum_score, score)

    def score_message(self, tokens):
        score = self.message_score

        users_mentioned = 0
        non_ascii = 0

        for token in tokens:
            if token.isupper():
                score += 0.05
                if token == '#FREENODE':
                    score += 0.3
                elif token.startswith('#'):
                    score += 0.1
                elif token == 'EL':
                    score += 0.2

            if token.strip(':') in self.known_users:
                users_mentioned += 1

            for char in token:
                if ord(char) > 127:
                    non_ascii += 1

        print(score, users_mentioned, non_ascii)

        if users_mentioned > 1:
            score += 0.05 * 2**users_mentioned
        if non_ascii > 1:
            score += 0.03 * 1.2**non_ascii

        return score

    def remove_user(self, user, _host, channel, score):
        self.conn.kick(channel, [user], 'spam: {}'.format(score))

    # Commands

    def reset_names(self, args, data):
        if data['nick'] not in self.admins:
            return

        self.known_users = set()

        sleep_len = 0

        for chan in self.conn.channels:
            self.conn.names(chan)

            time.sleep(sleep_len)
            if sleep_len < 0.8:
                sleep_len += 0.1

        self.conn.say('Done.', data['nick'])

    def show_names(self, args, data):
        if data['nick'] not in self.admins:
            return

        print(self.known_users)

        self.conn.say('Known users: {}'.format(len(self.known_users)), data['nick'])

    def reset_scores(self, args, data):
        if data['nick'] not in self.admins:
            return

        if args:
            for nick in args:
                self.user_scores.pop(nick, None)
        else:
            self.user_scores = {}

        self.conn.say('Done.', data['nick'])

    def show_scores(self, args, data):
        if data['nick'] not in self.admins:
            return

        if args:
            users = args
        else:
            users = sorted(self.user_scores, key=lambda k: -self.user_scores[k])[:5]

        msg = ', '.join('{}: {}'.format(k, self.user_scores.get(k)) for k in users)

        self.conn.say(msg, data['nick'])

    def add_admin(self, args, data):
        if data['nick'] not in self.admins:
            return

        self.admins |= set(args)

        self.conn.say('Done.', data['nick'])

    def join_channel(self, args, data):
        if data['nick'] not in self.admins:
            return

        for channel in args:
            self.conn.join(channel)

        self.conn.say('Done.', data['nick'])

    def leave_channel(self, args, data):
        if data['nick'] not in self.admins:
            return

        for channel in args:
            self.conn.leave('Bye', channel)

        self.conn.say('Done.', data['nick'])


if __name__ == '__main__':
    with open('config.json') as fileobj:
        config = json.load(fileobj)

    bot = Bot(lambda bot: Commands(bot, config), lambda: Ident(config))
    bot.main()
