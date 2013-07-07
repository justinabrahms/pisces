import functools
import json
import logging
import re
from werkzeug.exceptions import NotFound
from werkzeug.wrappers import Request, Response

log = logging.getLogger(__name__)

ALL_METHODS = ('GET', 'POST')


class Router(object):
    """
    A collection of Route objects.
    """
    # TODO(justinabrahms): Nested routers

    def __init__(self, endpoints):
        self.endpoints = endpoints

    def match(self, route, method):
        for endpoint in self.endpoints:
            if endpoint.handles_route(route, method):
                return endpoint.handle(route)


class Route(object):
    """
    A single mapping from url to a method on an instance.
    """

    def __init__(self, url, instance, method_str, methods=None):
        self._url = url
        self._re = self._compile_regex(url)
        self._instance = instance
        self._callback = method_str

        if methods is None:
            methods = ALL_METHODS
        self._methods = methods

    def handles_route(self, route, method):
        result = self._match(route) is not None and method in self._methods
        log.debug("Does %s %s match %s (aka '%s') in %s ? %s",
                  method, route,
                  self._url, self._re.pattern, self._methods, result)
        return result

    def _match(self, route):
        """Attempts to match a route to the bound regex. If it matches,
        returns a dictionary the matched params, otherwise None"""
        match = self._re.match(route)
        if match is not None:
            return match.groupdict()
        return None

    def _compile_regex(self, url):
        """
        Turns <foo> into (?P<foo>.*)
        """
        to_match = re.sub(r"(<.*?>)", r"(?P\1.*)", url)
        return re.compile("^%s$" % to_match)

    def handle(self, route):
        # TODO(justinabrahms): 3rd call to _match. Should it be cached?
        params = self._match(route)
        method = getattr(self._instance, self._callback)
        if method is None:
            raise AttributeError(
                "Unable to find %s on %s. Is something misconfigured?" % (
                    self._callback, self._instance))
        return functools.partial(method, **params)


class ArgProvider(object):
    """
    Used to pull values out of a `Request` object and provide them to the
    called method through argument introspection.

    Given args such as `get__param`, the prefix of this is `get` and the
    parameter is `param`.

    Fetching the value, in this case, would grab the `param` query parameter
    from `Request.args`
    """

    def get_prefix(self):
        """
        Returns the prefix the argument must have to match this.
        """
        raise NotImplementedError()

    def get_value(self, request, param):
        """
        Returns the `param` key from the `Request` object. What that actually
         means is implementation specific.
        """
        raise NotImplementedError()


class GetProvider(ArgProvider):
    _prefix = "get"

    def get_prefix(self):
        return self._prefix

    def get_value(self, request, param):
        return request.args.get(param)


class PostProvider(ArgProvider):
    _prefix = "post"

    def get_prefix(self):
        return self._prefix

    def get_value(self, request, param):
        return request.form.get(param)


class CookieProvider(ArgProvider):
    _prefix = "cookie"

    def get_prefix(self):
        return self._prefix

    def get_value(self, request, param):
        return request.cookies.get(param)


class ResponseConsumer(object):
    """
    Class which pulls values out of the dictionary response from a given view.
    It pulls things with a matching prefix and passes it to a registered
    handler.

    An example of this would be a return value of `'cookie__foo': 'bar'`
    would trigger the CookieConsumer which would set the `foo` cookie to have
     a value of `bar`.
    """

    def get_prefix(self):
        """
        Indicates which prefix string this consumer responds to.
        """
        raise NotImplementedError()

    def set_value(self, response, key, value):
        """
        Simple setter for the given consumer.
        """
        raise NotImplementedError()


class CookieHandler(ArgProvider, ResponseConsumer):
    _prefix = "cookie"

    # TODO(justinabrahms): how do we handle multiple cookie values set at once?
    def __init__(self, cookie_name="pisces_cookie"):
        self._cookie_name = cookie_name

    def get_prefix(self):
        return self._prefix

    def get_value(self, request, param):
        "Pulls the value from a given cookie"
        return request.cookies.get(param)

    def set_value(self, response, key, value):
        "Sets the value in a given cookie"
        if value is None:
            response.delete_cookie(key)
        else:
            response.set_cookie(self._cookie_name, value)


class AppContainer(object):
    """
    Adapter layer between WSGI and our Endpoint objects
    """

    def __init__(self, router, providers=None, consumers=None):
        self._routes = [router]
        if providers is None:
            providers = [PostProvider(), GetProvider(), CookieHandler()]
        self._arg_providers = providers
        if consumers is None:
            consumers = [CookieHandler()]
        self._consumers = consumers

    def wsgi_app(self, environ, start_response):
        """
        Main WSGI Interface
        """
        request = Request(environ)
        for route in self._routes:
            log.debug("Attempting route: %s", route)
            method = route.match(request.path, request.method)
            if method is None:
                continue

            ### EEW. Not sure I like this.
            extra_params = self._extract_params_from_request(method, request)

            value_map = method(**extra_params)
            if value_map is not None:
                # for now, we're doing dict only
                response = Response(mimetype="application/json")

                # EEW. It doesn't get any better on the response.
                self.apply_consumer_mutations(value_map, response)
                json_dump = json.dumps(value_map)
                response.data = json_dump
                return response(environ, start_response)
        raise NotFound()

    def _extract_params_from_request(self, method, request):
        """
        Pulls information out of the request and passes it to relevant
        methods. It uses a rather "magical" prefix syntax.

        `request__param` will pull the `param` value out of the Request's
        POST and returns it as a dictionary from request__param => value
        """
        passed_in_from_url_match = set()
        if method.keywords is not None:
            passed_in_from_url_match = set(method.keywords.keys())

        signature = set()

        import inspect

        argspec = inspect.getargspec(method.func)

        if argspec.args is not None:
            signature = signature.union(set(argspec.args))
        if argspec.keywords is not None:
            signature = signature.union(set(argspec.keywords))

        remaining_args = signature.difference(passed_in_from_url_match)
        remaining_args.discard('self')

        request_lookup_table = {}
        for provider in self._arg_providers:
            request_lookup_table[provider.get_prefix()] = provider

        extra_params = {}
        for param in remaining_args:
            try:
                key, value = param.split("__", 1)
                if key in request_lookup_table:
                    extra_params[param] = request_lookup_table[key].get_value(
                        request, value)
            except (ValueError,): # no __ in string
                pass
        return extra_params

    def apply_consumer_mutations(self, json_obj, response):
        """
        Takes values returned from the view, and pops them off the return
        value. This is used for things that need to affect the response in
        some way.
        """
        consumer_map = {}
        for consumer in self._consumers:
            consumer_map[consumer.get_prefix()] = consumer

        for key, value in json_obj.items():
            try:
                cmd, param = key.split("__", 1)
            except (ValueError,):
                continue
            try:
                consumer_map[cmd].set_value(response, param, value)
                del json_obj[key]
            except (KeyError,):
                continue

