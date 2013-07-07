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