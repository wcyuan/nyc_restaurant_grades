#!/usr/bin/env python
"""
"""

from __future__ import absolute_import, division, with_statement

import cgi
from datetime import datetime, date
import jinja2
import os
import re
import urllib
import urllib2
import webapp2
from collections import defaultdict

from google.appengine.ext import db
from google.appengine.api import users as gusers
from google.appengine.api import mail

jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))

# -------------------------------------------------------------------
# Reading DoH site
#

def parse_javascript(results):
    """
    Parse the JavaScript results containing restaurant grades.
    Returns a list of dicts, one dict per restaurant.  We really
    should use a real JavaScript parser here, but I couldn't get
    spidermonkey to compile on my mac and this hacky thing will do.

    The JavaScript on this site looks like this:

    var s0={};var s1={};var s2={};...
    s1.brghCode="1";s1.cuisineType="American ";...
    s2.brghCode="1";s2.cuisineType="Ice Cream, Gelato, Yogurt, Ices";...

    It appears to be code to set a bunch of hashes called s0, s1, s2,
    etc.

    So we parse this by translating it into a list of hashes, where
    the s0 hash is the 0th element of the list, the s1 hash is the 1st
    element, etc.
    """
    if not hasattr(parse_javascript, '_pattern'):
        # JavaScript lines of interest have form 's$NUM.$FIELD=$VAL'.
        parse_javascript._pattern = re.compile("^s(\d+)\.(\w+)=(.+)$")

    # The newlines are garbage - statements are semicolon-separated.
    lines = results.replace("\r\n", "").split(";")

    restaurants = []
    for line in lines:
        # We're just looking for lines like "s$NUM.$FIELD=$VAL".
        # We ignore all the other javascript for now...
        m = parse_javascript._pattern.match(line)
        if m:
            key, field, val = m.groups()
            key = int(key)
            if key >= len(restaurants):
                restaurants.extend({}
                                   for i in range(key - len(restaurants) + 1))
            r = restaurants[key]
            r[field] = val.strip('"')  # remove quotes from values

    return restaurants

def read_url(url, params, tohash=False):
    data = urllib2.urlopen(url, urllib.urlencode(params), 15000).read()
    if tohash:
        return parse_javascript(data)
    else:
        return data

def rss_url(method):
    return ("http://a816-restaurantinspection.nyc.gov/"
            "RestaurantInspection/dwr/call/plaincall/"
            "RestaurantSpringService.%s.dwr" % method)

def default_params(method, page):
    return {'callCount'       : '1',
            'page'            : '/RestaurantInspection/%s.do' % page,
            'httpSessionId'   : '',
            'scriptSessionId' : '${scriptSessionId}949',
            'c0-scriptName'   : 'RestaurantSpringService',
            'c0-methodName'   : method,
            'c0-id'           : '0',
            'batchId'         : '0'
            }

def find_restaurants(name=None, zipcode=None):
    """
    Download the restaurant grades for a given zipcode.
    Returns as a list of dicts, one dict per restaurant.
    """

    method = 'getResultsSrchCriteria'
    url = rss_url(method)
    params = default_params(method, 'SearchResults')
    # c0-param0=string:zipCode%20%3A_11201
    param0 = []
    if zipcode is not None:
        param0.append("zipCode :_%s" % zipcode)
    if name is not None:
        param0.append("name :%s" % name)
    params["c0-param0"] = "string:" + "\n".join(param0)
    params['c0-param1'] = 'string:'
    params['c0-param2'] = 'boolean:true'
    params['c0-param3'] = 'number:1'        # result set lowest number
    params['c0-param4'] = 'number:100000'   # result set highest number
                                            #   [20 in the official website]
                                            # There are about 28k restaurants total
    restaurants = read_url(url, params, tohash=True)
    for rest_hash in restaurants:
        rest_hash['camis']   = rest_hash['restCamis']
        rest_hash['name']    = rest_hash['restaurantName']
        rest_hash['zipcode'] = int(rest_hash['restZipCode'])
        rest_hash['street']  = rest_hash['stName']
        rest_hash['cuisine'] = rest_hash['cuisineType']
        rest_hash['grade']   = rest_hash['restCurrentGrade']
        rest_hash['score']   = int(rest_hash['scoreViolations']) 
        (month, day, year) = rest_hash['lastInspectedDate'].split('/')
        rest_hash['last_inspected'] = date(int(year), int(month), int(day))
    return restaurants

# -------------------------------------------------------------------
# Data models
#

class Restaurant(db.Model):
    """
    Models a subscription to a particular restaurant.
    """
    name     = db.StringProperty()
    zipcode  = db.IntegerProperty()
    street   = db.StringProperty()
    cuisine  = db.StringProperty()
    grade    = db.StringProperty()
    score    = db.IntegerProperty()
    last_inspected = db.DateProperty()
    prev_grade     = db.StringProperty()
    prev_score     = db.IntegerProperty()
    prev_inspected = db.DateProperty()
    last_updated   = db.DateTimeProperty()

    @classmethod
    def make_key(cls, camis):
        """
        Constructs a Datastore key for a restaurant.
        """
        return db.Key.from_path('Restaurant', camis)

class User(db.Model):
    last_notified = db.DateTimeProperty()
    email = db.StringProperty()

    @classmethod
    def make_key(cls, user_id):
        """
        Construct a User key from a user id
        """
        return db.Key.from_path('User', user_id)

class Subscription(db.Model):
    NOTIFY_CHOICES=["email", "sms", "none"]
    restaurant = db.ReferenceProperty(Restaurant,
                                      required=True)
    notify_grade_change = db.StringProperty(
        required=True,
        choices=set(NOTIFY_CHOICES))
    notify_score_change = db.StringProperty(
        required=True,
        choices=set(NOTIFY_CHOICES))
    notify_inspection_change = db.StringProperty(
        required=True,
        choices=set(NOTIFY_CHOICES))    

    @classmethod
    def make_key(cls, user_id, camis):
        """
        Construct a Subscription key from a user id and a restaurant
        id
        """
        return db.Key.from_path('User', user_id, 'Subscription', camis)

    @classmethod
    def color(cls, value):
        if value == 'none':
            return 'red'
        else:
            return 'green'

    @classmethod
    def text(cls, value):
        if value == 'none':
            return 'OFF'
        else:
            return 'ON'

    @property
    def grade_change_color(self):
        return self.color(self.notify_grade_change)

    @property
    def grade_change_button(self):
        return self.text(self.notify_grade_change)

    @property
    def score_change_color(self):
        return self.color(self.notify_score_change)

    @property
    def score_change_button(self):
        return self.text(self.notify_score_change)

    @property
    def inspection_change_color(self):
        return self.color(self.notify_inspection_change)

    @property
    def inspection_change_button(self):
        return self.text(self.notify_inspection_change)

    def needs_change_text(self, value):
        if value:
            return 'YES'
        else:
            return 'no'

    def needs_notify(self, field, prev_field, should_notify):
        """
        When a new restaurant is added, it is added with
        current grade == prev grade, so that we don't send
        notifications.

        Once something about the restaurant changes, the current value
        of the field will change, and the last_updated value will be
        updated and be more recent than the user's last notified
        field.
        """
        return ((self.parent().last_notified is None or
                 self.parent().last_notified < self.restaurant.last_updated)
                and should_notify != 'none'
                and field != prev_field)

    def needs_grade_notify(self):
        return self.needs_notify(self.restaurant.grade,
                                 self.restaurant.prev_grade,
                                 self.notify_grade_change)

    def grade_notify_text(self):
        return self.needs_change_text(self.needs_grade_notify())

    def needs_score_notify(self):
        return self.needs_notify(self.restaurant.score,
                                 self.restaurant.prev_score,
                                 self.notify_score_change)

    def score_notify_text(self):
        return self.needs_change_text(self.needs_score_notify())

    def needs_inspection_notify(self):
        return self.needs_notify(self.restaurant.last_inspected,
                                 self.restaurant.prev_inspected,
                                 self.notify_inspection_change)

    def inspection_notify_text(self):
        return self.needs_change_text(self.needs_inspection_notify())

# -------------------------------------------------------------------
# Pages
#

class HomePage(webapp2.RequestHandler):
    def update_user(self, user):
        user_obj = db.get(User.make_key(user.user_id()))
        if (user_obj and user_obj.email != user.email()):
            user_obj.email = user.email()
            user_obj.put()
            
    def get(self):
        user = gusers.get_current_user()
        if not user:
            self.redirect('/')

        self.update_user(user)

        subscriptions = Subscription.all().ancestor(
            User.make_key(user.user_id()))

        sort_key = self.request.get('sort')
        if sort_key == 'last_inspected':
            subscriptions = sorted(subscriptions, key=lambda s: s.restaurant.last_inspected)
        elif sort_key == 'score':
            subscriptions = sorted(subscriptions, key=lambda s: s.restaurant.score)
        elif sort_key == 'grade':
            subscriptions = sorted(subscriptions, key=lambda s: s.restaurant.grade)
        else:
            # by default, sort by name
            subscriptions = sorted(subscriptions, key=lambda s: s.restaurant.name)

        template = jinja_environment.get_template('home.html')
        self.response.out.write(template.render({
            'subscriptions': subscriptions,
            'logout_url': gusers.create_logout_url('/')
            }))

class FindPage(webapp2.RequestHandler):
    def get(self):
        user = gusers.get_current_user()
        if not user:
            self.redirect('/')

        subscriptions = Subscription.all(keys_only=True).ancestor(
            User.make_key(user.user_id()))
        ids = [k.id_or_name() for k in subscriptions]

        name    = self.request.get('name')
        zipcode = self.request.get('zipcode')
        restaurants = find_restaurants(name, zipcode)

        sort_key = self.request.get('sort')
        if sort_key is None:
            # by default, sort by name
            sort_key = 'name'
        if sort_key in rest_hash:
            restaurants = sorted(restaurants, key=lambda r: r[sort_key])

        for restaurant in restaurants:
            if restaurant['camis'] in ids:
                restaurant['action'] = "Remove"
            else:
                restaurant['action'] = "Add"

        template = jinja_environment.get_template('find.html')
        self.response.out.write(template.render({
            'restaurants': restaurants,
            'logout_url': gusers.create_logout_url('/')
            }))

class UpdateSubscriptionPage(webapp2.RequestHandler):
    def post(self):
        user = gusers.get_current_user()
        if not user:
            self.redirect('/')
        
        action = self.request.get('action')
        if action == 'RemoveUser':
            user_obj = db.get(User.make_key(user.user_id()))
            if user_obj is not None:
                user_obj.delete()
            subscriptions = Subscription.all().ancestor(User.make_key(user.user_id()))
            for sub in subscriptions:
                sub.delete()
            self.redirect('/home')
            return

        camis  = self.request.get('camis')
        goto   = self.request.get('goto')
        key = Subscription.make_key(user.user_id(), camis)
        subscription = db.get(key)
        if action == 'Add':
            if subscription is None:
                restaurant = db.get(Restaurant.make_key(camis))
                if restaurant is None:
                    name    = self.request.get('name')
                    zipcode = self.request.get('zipcode')
                    restaurants = find_restaurants(name, zipcode)
                    matches = [r for r in restaurants
                               if r['camis'] == camis]
                    if len(matches) == 1:
                        restaurant = Restaurant(
                            key_name=camis
                            ,name=matches[0]['name']
                            ,zipcode=matches[0]['zipcode']
                            ,street=matches[0]['street']
                            ,cuisine=matches[0]['cuisine']
                            ,grade=matches[0]['grade']
                            ,score=matches[0]['score']
                            ,last_inspected=matches[0]['last_inspected']
                            ,prev_grade=matches[0]['grade']
                            ,prev_score=matches[0]['score']
                            ,prev_inspected=matches[0]['last_inspected']
                            )
                        restaurant.last_updated = datetime.now()
                        restaurant.put()
                if restaurant != None:
                    user_ent = db.get(User.make_key(user.user_id()))
                    if user_ent is None:
                        user_ent = User(key_name=user.user_id(),
                                        email=user.email(),
                                        last_notified=datetime.now())
                        user_ent.put()
                    subscription = Subscription(
                        key_name=camis,
                        restaurant=restaurant,
                        notify_score_change='email',
                        notify_grade_change='email',
                        notify_inspection_change='email',
                        parent=user_ent)
                    subscription.put()
        elif action == 'Remove':
            if subscription is not None:
                subscription.delete()
        elif action == 'Change':
            if subscription is not None:
                field = self.request.get('field')
                changed = True
                if field == 'grade':
                    if subscription.notify_grade_change == 'none':
                        subscription.notify_grade_change = 'email'
                    else:
                        subscription.notify_grade_change = 'none'
                elif field == 'score':
                    if subscription.notify_score_change == 'none':
                        subscription.notify_score_change = 'email'
                    else:
                        subscription.notify_score_change = 'none'
                elif field == 'inspection':
                    if subscription.notify_inspection_change == 'none':
                        subscription.notify_inspection_change = 'email'
                    else:
                        subscription.notify_inspection_change = 'none'
                else:
                    changed = False
                if changed:
                    subscription.put()
        self.redirect(goto)

class UpdateRestaurantPage(webapp2.RequestHandler):
    def group_restaurants(self, restaurants):
        by_zipcode = defaultdict(list)
        for r in restaurants:
            by_zipcode[r.zipcode].append(r)
        return by_zipcode

    def update_one_restaurant(self, restaurant, update):
        changed = False
        if (restaurant.grade != update['grade'] or
            restaurant.score != update['score'] or
            restaurant.last_inspected != update['last_inspected']):
            changed = True
        if changed:
            restaurant.prev_score = restaurant.score
            restaurant.prev_grade = restaurant.grade
            restaurant.prev_inspected = restaurant.last_inspected
            for fld in ('name', 'zipcode', 'street', 'cuisine',
                        'grade', 'score', 'last_inspected'):
                setattr(restaurant, fld, update[fld])
            restaurant.last_updated = datetime.now()
            restaurant.put()

    def update_restaurants(self, restaurants):
        by_zipcode = self.group_restaurants(restaurants)
        for zipcode in by_zipcode:
            updated = find_restaurants(zipcode=zipcode)
            zipres = by_zipcode[zipcode]
            for update in updated:
                matches = [r for r in zipres
                           if r.key().id_or_name() == update['camis']]
                if len(matches) == 1:
                    self.update_one_restaurant(matches[0], update)

    def get(self):
        action = self.request.get('action')

        if action == 'update':
            camis   = self.request.get('camis')
            name    = self.request.get('name')
            zipcode = self.request.get('zipcode')
            restaurant = db.get(Restaurant.make_key(camis))
            self.update_restaurants([restaurant])
            self.redirect('/updateres')

        elif action == 'update_all':
            # make a note of used restaurants
            used = set()
            subscriptions = Subscription.all()
            for sub in subscriptions:
                used.add(sub.restaurant.key().id_or_name())

            # delete any unused restaurants
            restaurants = Restaurant.all()
            used_restaurants = []
            for r in restaurants:
                if r.key().id_or_name() in used:
                    used_restaurants.append(r)
                else:
                    r.delete()
            restaurants = used_restaurants

            # update restaurants
            self.update_restaurants(restaurants)
            self.redirect('/updateres')

        else:
            # We should optimize this.  If there are several
            # restaurants in the same zip code, we should update them
            # all at the same time, etc.
            restaurants = Restaurant.all()
            restaurants.get()
            template = jinja_environment.get_template('update.html')
            self.response.out.write(template.render({
                'restaurants': restaurants,
                'logout_url': gusers.create_logout_url('/')
                }))

class NotifyPage(webapp2.RequestHandler):
    def notify_user(self, user):
        subscriptions = Subscription.all().ancestor(user.key())
        for sub in subscriptions:
            if (user.last_notified is not None and
                user.last_notified > sub.restaurant.last_updated):
                continue
            messages = []
            if (sub.needs_grade_notify()):
                messages.append('%s changed its grade from %s to %s on %s' %
                                (sub.restaurant.name,
                                 sub.restaurant.prev_grade,
                                 sub.restaurant.grade,
                                 sub.restaurant.last_updated))
            if (sub.needs_score_notify()):
                messages.append('%s changed its score from %s to %s on %s' %
                                (sub.restaurant.name,
                                 sub.restaurant.prev_score,
                                 sub.restaurant.score,
                                 sub.restaurant.last_updated))
            if (sub.needs_inspection_notify()):
                messages.append('%s was inspected on %s' %
                                (sub.restaurant.name, sub.restaurant.last_inspected))
            if len(messages) == 0:
                continue
            body = "\n".join(messages)
            subject = '%s Updated!' % sub.restaurant.name
            mail.send_mail('notifier@nyc-restaurant-grades.appspotmail.com',
                           user.email, subject, body)
        user.last_notified = datetime.now()
        user.put()

    def get(self):
        action = self.request.get('action')
        goto   = self.request.get('goto')
        if goto is None:
            goto = '/notify'
        if action == "notify_all":
            users = User.all()
            for user in users:
                self.notify_user(user)
            self.redirect(goto)
        elif action == "notify_user":
            user_id = self.request.get('user_id')
            if user_id is not None and user_id != '':
                # XXX don't know why, but this doesn't work, it
                # doesn't find the user
                user = db.get(User.make_key(user_id))
                if user is not None:
                    self.notify_user(user)
            self.redirect(goto)
        else:
            user_id = self.request.get('user_id')
            if user_id is not None and user_id != '':
                # XXX don't know why, but this doesn't work, it
                # doesn't find the user
                user = db.get(User.make_key(user_id))
            else:
                user = None
            if user is not None:
                users = [user]
                goto = '/notify?user=%s' % user_id
            else:
                users = User.all()
                goto = '/notify'
            display_users = []
            for user in users:
                subscriptions = Subscription.all().ancestor(user.key())
                display_user = {'user_id': user.key().id_or_name()
                                ,'email': user.email
                                ,'last_notified': user.last_notified
                                ,'subscriptions': [s for s in subscriptions]
                                }
                display_users.append(display_user)
            template = jinja_environment.get_template('notify.html')
            self.response.out.write(template.render({
                'users': display_users,
                'logout_url': gusers.create_logout_url('/'),
                'goto': goto
                }))

class GotoRestaurantPage(webapp2.RequestHandler):
    def get(self):
        camis = self.request.get('camis')
        template = jinja_environment.get_template('goto.html')
        self.response.out.write(template.render({
            'camis': camis,
            }))

# -------------------------------------------------------------------
# webapp

app = webapp2.WSGIApplication(
    [('/home',        HomePage)
     ,('/find',       FindPage)
     ,('/updatesub',  UpdateSubscriptionPage)
     ,('/updateres',  UpdateRestaurantPage)
     ,('/notify',     NotifyPage)
     ,('/goto',       GotoRestaurantPage)
     ],
    debug=True)

