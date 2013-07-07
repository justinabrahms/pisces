# Pisces: A testable web framework

Pisces is a Python web framework with two goals in mind:

1. Application code should be easy to test.
2. Components should separate concerns where possible.

[![Build Status](https://travis-ci.org/justinabrahms/pisces.png)](https://travis-ci.org/justinabrahms/pisces)

## What does it look like?

Pisces is fairly simple and looks a lot like vanilla python code. A fully
working API for a URL shortener looks something like this.


```python
import base64
import logging
import pinject
import redis

from pisces import Router, Route, AppContainer


class ShorteningService(object):
    """High-level data retrieval / persistance interface"""

    def __init__(self, data_store):
        # redis, in this example, but implementation specific
        self._backend = data_store

    def hash_link(self, link):
        return base64.b32encode(link)

    def persist_hash_link_pair(self, short_id, link):
        self._backend.set('url-target:' + short_id, link)

    def track_view(self, short_id):
        self._backend.incr('click-count:' + short_id)

    def get_view_count(self, short_id):
        return self._backend.get('click-count:' + short_id)

    def get_url_by_hash(self, short_id):
        return self._backend.get('url-target:' + short_id)


class ShorteningEndpoint(object):
    """Thin layer for munging data from request to backend and back"""

    def __init__(self, shortening_service):
        self._service = shortening_service

    def index(self):
        return {'message': 'WELCOME'}

    # This post__ is a sneaky thing where we pull the url param out of the
    # post data.
    def new_url(self, post__url):
        short_id = self._service.hash_link(post__url)
        self._service.persist_hash_link_pair(short_id, post__url)
        return {'hash': short_id}

    def follow_url(self, short_id):
        url = self._service.get_url_by_hash(short_id)
        self._service.track_view(short_id)
        return {'url': url}

    def details(self, short_id):
        count = self._service.get_view_count(short_id)
        url = self._service.get_url_by_hash(short_id)
        return {
            'count': count,
            'url': url
        }


class ShortBindingSpec(pinject.BindingSpec):
    def provide_data_store(self, config):
        return redis.Redis(config.get('host'), config.get('port'))

    def provide_config(self):
        # fetch config from file
        return {'host': '127.0.0.1', 'port': 6379}


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    # not satisfied with this API yet
    graph = pinject.new_object_graph(binding_specs=[ShortBindingSpec()])
    short_endpoint = graph.provide(ShorteningEndpoint)

    root_router = Router([
        Route('/', short_endpoint, 'index', methods=['GET']),
        Route('/', short_endpoint, 'new_url', methods=['POST']),
        Route('/<short_id>\+', short_endpoint, 'details'),
        Route('/<short_id>', short_endpoint, 'follow_url'),
    ])

    app_container = AppContainer(root_router)

    from werkzeug.serving import run_simple

    run_simple('127.0.0.1', 5000, app_container.wsgi_app, use_reloader=True,
               use_debugger=True)
```

## Example Explained

To break this down, the ShorteningService implements our core backend logic.
It offers readable method names that express the intention of the method call,
and is not littered with implementation concerns. It is, for all purposes, a
dull representation of business logic.

The ShorteningEndpoint is a class which represents various endpoints. The
responsibility of this class is to ferry information from method parameters
(provided by either the route or custom preprocessors) into the business
objects, and return values to the client.

ShortBindingSpec tells [pinject](https://github.com/google/pinject) how to
provide arguments for object instantiation. Pinject is a dependency injection
framework, which makes code more testable by making it easier to stub out
dependencies.

In the `__main__` method, we setup logging and get an instance of our endpoint
from pinject. We use this instance to build a routing table. A routing table
is based on a `Router` object which takes a list of `Route` objects. These
`Route` objects map a path to a method on an endpoint instance. You can
optionally say which HTTP methods are supported. The urls within the less than
and greater than symbols represents capturing groups. These will be passed on
to your methods as keyword arguments.

Using this routing table, we instantiate an `AppContainer` which represents a
bridge between the application code you've defined and the WSGI interface. We
can attach this `AppContainer` to [werkzeug](werkzeug.pocoo.org/docs/)'s run
server.

## Custom Processors

There are two types of processors defined in pisces: `ArgProvider`s and
`ResponseConsumer`s. `ArgProvier`s are responsible for providing keyword
arguments to a method call and `ResponseConsumer`s take arguments from the
return value and augment the response to the client.

`ArgProvider`s take a custom prefix and, if something matches, provide a value
based on the key. In the example of `get__param`, we will look for a `param`
value in the HTTP GET querystring and provider as a keyword argument to the
function as `get__param`.

`ResponseConsumer`s do a very similar task for responses. They read the keys
of the dict returned by views, run them through the `ResponseConsumer` list
augmenting the internal `werkzeug.Response` object. Any keys that are matched
are popped off of the returned dict before sending it back to the client as
JSON data.
