Intro
-----

This is a Google App Engine application.  

[https://developers.google.com/appengine/](https://developers.google.com/appengine)

Github uses markdown.  The syntax is described
[here](http://daringfireball.net/projects/markdown/syntax).  You can
test markdown
[here](http://daringfireball.net/projects/markdown/dingus).

Basic syntax:

 - \_italic_

 - \**bold**

 - \[link text](http://url/ "Title")

Basic Design
------------

Each user has a list of restaurants that they subscribe to.  Users can
search for new restaurants to add to the list and remove restaurants
from it.

Pages:

 - **index.html** - Introduction and login

 - **home.html** - Lists all the restaurants you are subscribed to.
 Options to remove restaurants or to modify the events that you are
 notified for.

 - **find.html** - Search for restaurants to add.

 - **update.html** - (_For administrators only_) Update information about a
 restaurant.  Runs by cron once a day to update all restaurants.

 - **notify.html** - (_For administrators only_) Notify users about changes
 to a restaurant.  Runs by cron once a day to notify all users for
 changes.

Running a development server
----------------------------
  dev_appserver.py [--port=<port>] <path>

Path is the path to the directory containing the app.  Port defaults
to 8080.

Uploading to production
-----------------------
  appcfg.py --oauth2 --noauth_local_webserver --no_cookies update nyc_restaurant_grades/

Todo
----
Allow sorting of list of restaurants by different columns.

