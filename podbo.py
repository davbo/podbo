import feedparser
import time

from datetime import datetime
from flask import Flask, render_template
from flaskext.sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
db = SQLAlchemy(app)


@app.route('/')
def index():
    feeds = Feed.query.all()
    return render_template('index.html', feeds=feeds)

class Feed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(120), unique=True)
    title = db.Column(db.String(80))
    summary = db.Column(db.String(300))

    def __init__(self, url):
        feed = feedparser.parse(url)
        self.url = url
        self.title = feed['feed']['title']
        self.summary = feed['feed']['summary']

    def get_entries(self):
        feed = feedparser.parse(self.url)
        entries = []
        for entry in feed['entries']:
            e = dict()
            e['pub_date'] = datetime.fromtimestamp(
                    time.mktime(entry['updated_parsed']))
            e['title'] = entry['title']
            for mc in entry['media_content']:
                if mc['type'].startswith('audio'):
                    e['media_url'] = mc['url']
            if not 'media_url' in e:
                e['media_url'] = entry['media_content'][0]['url']
            e['feed'] = self
            entries.append(Entry(**e))
        return entries

class Entry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(80))
    media_url = db.Column(db.String(150))
    pub_date = db.Column(db.DateTime)

    feed_id = db.Column(db.Integer, db.ForeignKey('feed.id'))
    feed = db.relationship('Feed',
        backref=db.backref('entries', lazy='dynamic'))

    def __init__(self, title="", media_url="", pub_date=None, feed=None):
        self.title = title
        self.media_url = media_url
        self.pub_date = pub_date
        self.feed = feed

if __name__ == '__main__':
    app.debug = True
    app.run()
