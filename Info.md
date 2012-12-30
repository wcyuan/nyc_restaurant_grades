Intro
-----

This is a Google App Engine application.  It uses the webapp2 framework.

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

 - **home** - Lists all the restaurants you are subscribed to.
 Options to remove restaurants or to modify the events that you are
 notified for.

 - **find** - Search for restaurants to add.

 - **update** - (_For administrators only_) Update information about a
 restaurant.  Runs by cron once a day to update all restaurants.

 - **notify** - (_For administrators only_) Notify users about changes
 to a restaurant.  Runs by cron once a day to notify all users for
 changes.

Running a development server
----------------------------
  dev_appserver.py [--port=<port>] <path>

where <path> is the path to the directory containing the app.  Port
defaults to 8080.  e.g.

  dev_appserver.py nyc_restaurant_grades/

Access the server at http://localhost:8080/

Uploading to production
-----------------------
  appcfg.py --oauth2 --noauth_local_webserver --no_cookies update <path>

where <path> is the path to the directory containing the app, e.g.

  appcfg.py --oauth2 --noauth_local_webserver --no_cookies update nyc_restaurant_grades/

This will display a url for a page where you can give appcfg.py access
to your account.  It will then prompt for a secret key.  If you point
a browser to the url, and verify the access, it will send you to a
page containing that secret key.  Copy it and paste it back in the
waiting terminal.  The upload will continue, and it will check to
make sure it succeeded.  It usually takes about a minute.

Todo
----
Allow sorting of list of restaurants by different columns.

