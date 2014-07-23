from flask import request, url_for
from math import ceil
# noinspection PyUnresolvedReferences
from flask.ext.wtf import Form
from wtforms import TextField
from wtforms.validators import Optional

from app import app


def url_for_other_page(page):
    #args = request.view_args.copy()
    args = dict(request.view_args.items() + request.args.to_dict().items())
    args['page'] = page
    return url_for(request.endpoint, **args)
app.jinja_env.globals['url_for_other_page'] = url_for_other_page


@app.template_filter("nowrap")
def nowrap_filter(text):
    return '<span style="white-space: nowrap">' + text + '</span>'


@app.template_filter("datetime")
def datetime_filter(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


class Pagination(object):
    def __init__(self, page, per_page, total_count):
        self.page = page
        self.per_page = per_page
        self.total_count = total_count

    @property
    def pages(self):
        return int(ceil(self.total_count / float(self.per_page)))

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def start_index(self):
        return (self.page - 1) * self.per_page + 1

    def iter_pages(self, left_edge=2, left_current=2,
                   right_current=5, right_edge=2):
        last = 0
        for num in xrange(1, self.pages + 1):
            if num <= left_edge or \
                    (self.page - left_current - 1 < num < self.page + right_current) or \
                            num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num


class SearchForm(Form):
    title = TextField('title', description="title", validators=[Optional()])
    author = TextField('author', description="author", validators=[Optional()])
