#!/usr/bin/env python3

import os
import uuid
import json
import sqlite3
import traceback

from tornado import web, ioloop, websocket

class DB:
    def __init__(self, db_path):
        self._db_path = db_path
        self._con = self._get_db_connection()
        self._con.row_factory = sqlite3.Row
        self._cur = self._con.cursor()
        self._ensure_tables()

    def select(self, sql, params=[]):
        self._execute(sql, params)
        return self._cur.fetchall()

    def insert(self, sql, params=[]):
        self._execute(sql, params)
        return self._cur.lastrowid

    def update(self, sql, params=[]):
        self._execute(sql, params)

    def delete(self, sql, params=[]):
        self._execute(sql, params)

    def _execute(self, sql, params=[]):
        self._cur.execute(sql, params)

    def commit(self):
        self._con.commit()

    def _get_db_connection(self):
        path = self._db_path
        if not os.path.isfile(path):
            fd = os.open(path, os.O_CREAT, mode=0o600)
            os.close(fd)
        return sqlite3.connect(path, check_same_thread=False)

    def _ensure_tables(self):
        self._execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                token TEXT NOT NULL
            )
        ''')
        self._execute('CREATE INDEX IF NOT EXISTS user_token_idx ON users (token)')
        self._execute('''
            CREATE TABLE IF NOT EXISTS polls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        self._execute('CREATE INDEX IF NOT EXISTS poll_user_id_idx ON polls (user_id)')
        self._execute('''
            CREATE TABLE IF NOT EXISTS choices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                FOREIGN KEY(poll_id) REFERENCES polls(id),
                UNIQUE (poll_id, name)
            )
        ''')
        self._execute('CREATE INDEX IF NOT EXISTS choice_poll_id_idx ON choices (poll_id)')
        self._execute('''
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                choice_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                FOREIGN KEY(choice_id) REFERENCES choices(id),
                FOREIGN KEY(user_id) REFERENCES users(id),
                UNIQUE (choice_id, user_id)
            )
        ''')
        self._execute('CREATE INDEX IF NOT EXISTS vote_choice_id_idx ON votes (choice_id)')
        self._execute('CREATE INDEX IF NOT EXISTS vote_user_id_idx ON votes (user_id)')
        self.commit()

db = DB('app.db')

def auth(handler):
    token = handler.get_cookie('token', '')
    res = db.select('select * from users where token = ?', [token])
    if not res:
        return None
    user_id = res[0]['id']
    return user_id

def serialize(rows):
    return json.dumps([dict(r) for r in rows]).encode('utf-8')

def notify_subscribers(handler, poll_id):
    i = 0
    clients = handler._clients.get(str(poll_id)) or []
    while i < len(clients):
        client = clients[i]
        try:
            client.write_message({'type': 'vote'})
        except:
            clients.remove(client)
            i -= 1
            traceback.print_exc()
        i += 1

class UserHandler(web.RequestHandler):
    def get(self):
        user_id = auth(self)
        users = db.select('select id, name from users where id = ?', [user_id])
        self.write(serialize(users))

    def post(self):
        user_id = auth(self)
        name = self.get_argument('name', '')
        if user_id:
            db.update('update users set name = ? where id = ?', [name, user_id])
            db.commit()
        else:
            token = str(uuid.uuid4())
            try:
                db.insert(
                    'insert into users (name, token) values (?, ?)',
                    [name, token]
                )
                db.commit()
            except sqlite3.IntegrityError:
                raise web.HTTPError(409)
            self.set_cookie('token', token)

class PollHandler(web.RequestHandler):
    def get(self):
        polls = db.select('select * from polls')
        self.write(serialize(polls))

    def post(self):
        user_id = auth(self)
        if not user_id:
            raise web.HTTPError(403)
        name = self.get_argument('name', '')
        row_id = db.insert('insert into polls (user_id, name) values (?, ?)', [user_id, name])
        db.commit()
        self.write(str(row_id))

class ChoiceHandler(web.RequestHandler):
    def initialize(self, clients):
        self._clients = clients

    def get(self):
        poll_id = self.get_argument('poll_id', '')
        choices = db.select('select * from choices where poll_id = ?', [poll_id])
        self.write(serialize(choices))

    def post(self):
        # TODO permissions
        user_id = auth(self)
        if not user_id:
            raise web.HTTPError(403)
        poll_id = self.get_argument('poll_id', '')
        if not db.select('select * from polls where id = ?', [poll_id]):
            raise web.HTTPError(404)
        name = self.get_argument('name', '').strip()
        if not name:
            raise web.HTTPError(400)
        try:
            db.insert(
                'insert into choices (poll_id, name) values (?, ?)',
                [poll_id, name]
            )
            db.commit()
        except sqlite3.IntegrityError:
            raise web.HTTPError(409)
        notify_subscribers(self, poll_id)

class VoteHandler(web.RequestHandler):
    def initialize(self, clients):
        self._clients = clients

    def get(self):
        user_id = auth(self)
        poll_id = self.get_argument('poll_id', '')
        votes = db.select('''
            select
                c.id as choice_id,
                count(*) as vote_count,
                sum(v.user_id = ?) as voted
            from votes v
            join choices c on v.choice_id = c.id
            where c.poll_id = ?
            group by c.id
        ''', [user_id, poll_id])
        self.write(serialize(votes))

    def post(self):
        user_id = auth(self)
        choice_id = self.get_argument('choice_id', '')
        if not (rows := db.select('select * from choices where id = ?', [choice_id])):
            raise web.HTTPError(404)
        poll_id = rows[0]['poll_id']
        if db.select('select * from votes where user_id = ? and choice_id = ?', [user_id, choice_id]):
            db.delete('delete from votes where user_id = ? and choice_id = ?', [user_id, choice_id])
            db.commit()
        else:
            try:
                db.insert(
                    'insert into votes (choice_id, user_id) values (?, ?)',
                    [choice_id, user_id]
                )
                db.commit()
            except sqlite3.IntegrityError:
                raise web.HTTPError(409)
        notify_subscribers(self, poll_id)

class VoterHandler(web.RequestHandler):
    def get(self):
        poll_id = self.get_argument('poll_id', '')
        voters = db.select('''
            select u.name
            from votes v
            join choices c on v.choice_id = c.id
            join users u on v.user_id = u.id
            where c.poll_id = ?
            group by u.id
        ''', [poll_id])
        self.write(serialize(voters))

class EventSubscriptionHandler(websocket.WebSocketHandler):
    def initialize(self, clients):
        self._clients = clients

    def check_origin(self, origin):
        return True

    def open(self):
        poll_id = self.get_argument('poll_id', '')
        if poll_id not in self._clients:
            self._clients[poll_id] = []
        self._clients[poll_id].append(self)

    def on_close(self):
        poll_id = self.get_argument('poll_id', '')
        self._clients[poll_id].remove(self)

def main():
    clients = {}
    app = web.Application([
        (r'/users', UserHandler),
        (r'/polls', PollHandler),
        (r'/votes', VoteHandler, {'clients': clients}),
        (r'/voters', VoterHandler),
        (r'/choices', ChoiceHandler, {'clients': clients}),
        (r'/events', EventSubscriptionHandler, {'clients': clients}),
        (
            r'/(.*)',
            web.StaticFileHandler,
            dict(path='client/', default_filename='index.html')
        ),
    ])
    app.listen(8080)
    ioloop.IOLoop.instance().start()

if __name__ == '__main__':
    main()
