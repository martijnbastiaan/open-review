"""
This module contains convenience functions for testing purposes. For more information see:

    https://github.com/open-review/open-review/wiki/Testing

"""
from contextlib import contextmanager
from functools import wraps
import functools
import unittest
from datetime import datetime
from logging import getLogger

from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import connection
from django.test import LiveServerTestCase
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.wait import WebDriverWait

from openreview.apps.accounts.models import User
from openreview.apps.main.models import Author, Paper, Keyword, Review, Vote, Category
from openreview.apps.tools.string import get_bool

log = getLogger(__name__)

# Determine the WebDriver module. Defaults to Firefox.
try:
    web_driver_module = settings.SELENIUM_WEBDRIVER
except AttributeError:
    from selenium.webdriver.firefox import webdriver as web_driver_module

class SeleniumWebDriver(web_driver_module.WebDriver):
    """Default webdriver, extended with convenience methods."""

    def find_css(self, css_selector):
        """Shortcut to find elements by CSS. Returns either a list or singleton"""
        elems = self.find_elements_by_css_selector(css_selector)
        found = len(elems)
        if found == 1:
            return elems[0]
        elif not elems:
            raise NoSuchElementException(css_selector)
        return elems

    def wait_for_css(self, css_selector, timeout=7):
        """Shortcut for WebDriverWait"""
        try:
            return WebDriverWait(self, timeout).until(lambda driver: driver.find_css(css_selector))
        except TimeoutException:
            self.quit()

_skip_msg = "Selenium test cases are disabled due to the presence of environment variable SKIP_SELENIUM_TESTS."
skip = functools.partial(get_bool, "SKIP_SELENIUM_TESTS", False)
same_browser = functools.partial(get_bool, "SELENIUM_SAME_BROWSER", False)

if not skip() and same_browser():
    WEBDRIVER = SeleniumWebDriver()

class SeleniumTestCase(LiveServerTestCase):
    """TestCase for in-browser testing. Sets up `wd` property, which is an initialised Selenium
    webdriver (defaults to Firefox)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __getattribute__(self, item):
        obj = super().__getattribute__(item)

        if item.startswith("test_") and callable(obj) and skip():
            return functools.partial(unittest.skip, _skip_msg)
        return obj

    @property
    def wd(self):
        return WEBDRIVER if same_browser() else self._wd

    def tearDown(self):
        if not skip():
            self.wd.delete_all_cookies()
        super().tearDown()

    @classmethod
    def setUpClass(cls):
        if not skip() and not same_browser():
            cls._wd = SeleniumWebDriver()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        if not skip():
            cls._wd.quit()
        super().tearDownClass()

    if same_browser() and not skip():
        # HACK: Prevents live server from shutting down, which will generate an error if
        # we're running a webdriver (for some obscure reason). After running tests these
        # loose daemons are cleaned up by the operating system.
        @classmethod
        def tearDownClass(cls):
            pass

    def open(self, url):
        self.wd.get("%s%s" % (self.live_server_url, url))

    def login(self, username=None, password="test"):
        if username is None:
            username = create_test_user(password="test").username

        self.logout()
        self.open(reverse("accounts-login"))
        self.wd.find_css("#id_login_username").send_keys(username)
        self.wd.find_css("#id_login_password").send_keys(password)
        self.wd.find_css('input[value="Login"]').click()
        self.wd.wait_for_css("body")

    def logout(self):
        self.open(reverse("accounts-logout"))
        self.wd.wait_for_css("body")

# This is a hack to generate unique names for test models
COUNTER = 0
def up_counter(func):
    @wraps(func)
    def inner(*args, **kwargs):
        global COUNTER
        COUNTER += 1
        return func(*args, **kwargs)
    return inner

@up_counter
def create_test_user(**kwargs):
    return User.objects.create_user(**dict({
        "username": "user-%s" % COUNTER,
        "password": "test"
    }, **kwargs))

@up_counter
def create_test_author(**kwargs):
    return Author.objects.create(**dict({"name": "author-%s" % COUNTER}, **kwargs))

@up_counter
def create_test_keyword(label="keyword - %s"):
    return Keyword.objects.create(label=label % COUNTER)

@up_counter
def create_test_paper(n_authors=0, n_keywords=0, n_comments=0, n_reviews=0, n_categories=0, **kwargs):
    paper = Paper.objects.create(**dict({"title": "paper-%s" % COUNTER, "abstract": "abstract"}, **kwargs))

    if n_categories > 0:
        for i in range(n_categories):
            paper.categories.add(create_test_category())

    if n_authors > 0:
        for i in range(n_authors):
            paper.authors.add(create_test_author())

    if n_keywords > 0:
        for i in range(n_keywords):
            paper.keywords.add(create_test_keyword())

    if n_reviews > 0:
        for i in range(n_reviews):
            create_test_review(paper=paper)

    if n_comments > 0:
        if paper.reviews.count() == 0:
            create_test_review(paper=paper)

        review = paper.reviews.all()[0]
        for i in range(n_comments):
            create_test_review(parent=review, paper=paper)

    return paper

@up_counter
def create_test_review(**kwargs):
    paper, poster = None, None
    if "paper" not in kwargs:
        if "parent" in kwargs:
            paper = kwargs["parent"].paper
        else:
            paper = create_test_paper()
    if "poster" not in kwargs:
        poster = create_test_user()

    return Review.objects.create(**dict({
        "text": "review content",
        "poster": poster,
        "paper": paper,
        "timestamp": datetime.now(),
        "rating": 4
    }, **kwargs))

@up_counter
def create_test_keyword(**kwargs):
    return Keyword.objects.create(**dict({"label": "keyword-%s" % COUNTER}, **kwargs))

def create_test_vote(**kwargs):
    user, review = None, None

    if "review" not in kwargs:
        review = create_test_review()
    if "user" not in kwargs:
        user = create_test_user()

    return Vote.objects.create(**dict({
        "vote": 1,
        "voter": user,
        "review": review
    }, **kwargs))

def create_test_votes(counts=None, review=None):
    """
    Counts is a dictionary with vote : amount. The following dict:

        >>> { -1: 25, 1: 4, 0: 5 }

    would create 25 downvotes, 4 upvotes and 5 neutral votes.
    """
    if review is None:
        review = create_test_review()

    if counts is None:
        return

    for vote, times in counts.items():
        for i in range(times):
            create_test_vote(review=review, vote=vote)

    return review

@up_counter
def create_test_category(**kwargs):
    category = Category(**dict({
        "name": "category-%s" % COUNTER,
        "arxiv_code": "arxiv-%s" % COUNTER,
        "parent": None
    }, **kwargs))
    category.save(test_environment=True)
    return category

@contextmanager
def assert_max_queries(n=0):
    """
    Raise AssertionError if code in contextmanager exceeds `n` queries. Example usage:

    >>> with assert_max_queries(n=1):
    >>>     list(Paper.objects.all())

    @param n: code can use at most `n` queries
    @type n: int
    """
    queries = []
    with list_queries(destination=queries, log_output=False):
        yield

    nqueries = len(queries)
    if nqueries > n:
        msg = "Should take at most {n} queries, but took {nqueries}.".format(**locals())
        for i, query in enumerate(queries):
            sql, time = query["sql"], query["time"]
            msg += "\n[{i}] {sql} ({time})".format(**locals())
        raise AssertionError(msg)

@contextmanager
def list_queries(destination=None, log_output=True, ignore=("QUERY = 'BEGIN' - PARAMS = ()",)):
    """
    Context manager which makes it easy to retrieve executed queries regardless of the
    value of settings.DEBUG. Usage example:

    >>> with list_queries() as queries:
    >>>     Paper.objects.all()
    >>> print(queries)

    @param destination: append queries to this object
    @type destination: list

    @param ignore: sql queries to ignore (default: sqlite BEGIN)
    @type ignore: list / tuple

    @param log_output: should we log queries to log.debug?
    @type log_output: bool
    """
    nqueries = len(connection.queries)

    # We need to set debug to let Django record queries
    debug_prev = settings.DEBUG
    settings.DEBUG = True

    if destination is None:
        destination = []

    try:
        yield destination
        queries = connection.queries[nqueries:]
        queries = [q for q in queries if q["sql"] not in ignore]
        destination += queries
    finally:
        settings.DEBUG = debug_prev

        if log_output:
            for query in queries:
                log.debug(query)


