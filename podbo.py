import feedparser
import time

from datetime import datetime
from flask import Flask, render_template, g, session, request, redirect, flash, url_for, abort
from flaskext.openid import OpenID
from flaskext.sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
app.config['SECRET_KEY'] = 'dev key'
db = SQLAlchemy(app)
oid = OpenID()

@app.before_request
def before_request():
    g.user = None
    if 'openid' in session:
        g.user = User.query.filter_by(openid=session['openid']).first()

@app.after_request
def after_request(response):
    db.session.remove()
    return response

@app.route('/')
def index():
    if g.user:
        feeds = g.user.subscriptions
        recently_played = g.user.played
        return render_template('index.html', feeds=feeds, recently_played=recently_played)
    else:
        feeds = Feed.query.all()
        return render_template('index.html', feeds=feeds)

@app.route('/directory', methods=['GET', 'POST'])
def directory():
    if request.method == 'POST':
        # TODO:  accept list of boolean checkbox inputs
        pass
    feeds = Feed.query.all()
    return render_template('directory.html', feeds=feeds)

@app.route('/add_feed', methods=['GET', 'POST'])
def add_feed():
    if request.method == 'POST':
        feed_url = request.form['feed_url']
        feed = Feed(feed_url)
        feed.get_entries()
        db.session.add(feed)
        db.session.commit()
        flash(u'Added feed: %s' % feed.title)
    return render_template('add_feed.html')

@app.route('/login', methods=['GET', 'POST'])
@oid.loginhandler
def login():
    """Does the login via OpenID.  Has to call into `oid.try_login`
    to start the OpenID machinery.
    """
    # if we are already logged in, go back to were we came from
    if g.user is not None:
        return redirect(oid.get_next_url())
    if request.method == 'POST':
        openid = request.form.get('openid')
        if openid:
            return oid.try_login(openid, ask_for=['email', 'fullname',
                                                  'nickname'])
    return render_template('login.html', next=oid.get_next_url(),
                           error=oid.fetch_error())

@oid.after_login
def create_or_login(resp):
    """This is called when login with OpenID succeeded and it's not
    necessary to figure out if this is the users's first login or not.
    This function has to redirect otherwise the user will be presented
    with a terrible URL which we certainly don't want.
    """
    session['openid'] = resp.identity_url
    user = User.query.filter_by(openid=resp.identity_url).first()
    if user is not None:
        flash(u'Successfully signed in')
        g.user = user
        return redirect(oid.get_next_url())
    return redirect(url_for('create_profile', next=oid.get_next_url(),
                            name=resp.fullname or resp.nickname,
                            email=resp.email))

@app.route('/create-profile', methods=['GET', 'POST'])
def create_profile():
    """If this is the user's first login, the create_or_login function
    will redirect here so that the user can set up his profile.
    """
    if g.user is not None or 'openid' not in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        if not name:
            flash(u'Error: you have to provide a name')
        elif '@' not in email:
            flash(u'Error: you have to enter a valid email address')
        else:
            flash(u'Profile successfully created')
            db.session.add(User(name, email, session['openid']))
            db.session.commit()
            return redirect(oid.get_next_url())
    return render_template('create_profile.html', next_url=oid.get_next_url())

@app.route('/profile', methods=['GET', 'POST'])
def edit_profile():
    """Updates a profile"""
    if g.user is None:
        abort(401)
    form = dict(name=g.user.name, email=g.user.email)
    if request.method == 'POST':
        if 'delete' in request.form:
            db.session.delete(g.user)
            db.session.commit()
            session['openid'] = None
            flash(u'Profile deleted')
            return redirect(url_for('index'))
        form['name'] = request.form['name']
        form['email'] = request.form['email']
        if not form['name']:
            flash(u'Error: you have to provide a name')
        elif '@' not in form['email']:
            flash(u'Error: you have to enter a valid email address')
        else:
            flash(u'Profile successfully created')
            g.user.name = form['name']
            g.user.email = form['email']
            db.session.commit()
            return redirect(url_for('edit_profile'))
    return render_template('edit_profile.html', form=form)

@app.route('/logout')
def logout():
    session.pop('openid', None)
    flash(u'You have been signed out')
    return redirect(oid.get_next_url())

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60))
    email = db.Column(db.String(200))
    openid = db.Column(db.String(200))
    subscriptions = db.relationship("Subscription")
    played = db.relationship("Progress")

    def __init__(self, name, email, openid):
        self.name = name
        self.email = email
        self.openid = openid

class Feed(db.Model):
    __tablename__ = 'feeds'
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
    __tablename__ = 'entries'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(80))
    media_url = db.Column(db.String(150))
    pub_date = db.Column(db.DateTime)

    feed_id = db.Column(db.Integer, db.ForeignKey('feeds.id'))
    feed = db.relationship('Feed',
        backref=db.backref('entries', lazy='dynamic'))

    def __init__(self, title="", media_url="", pub_date=None, feed=None):
        self.title = title
        self.media_url = media_url
        self.pub_date = pub_date
        self.feed = feed

class Subscription(db.Model):
    feed_id = db.Column(db.Integer, db.ForeignKey('feeds.id'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    feed = db.relationship("Feed")

class Progress(db.Model):
    seconds = db.Column(db.Integer)
    last_played = db.Column(db.DateTime)

    entry_id = db.Column(db.Integer, db.ForeignKey('entries.id'), primary_key=True)
    entry = db.relationship("Entry")
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)


if __name__ == '__main__':
    app.debug = True
    app.run()
