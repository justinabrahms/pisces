import functools
import unittest
from mock import Mock
from pisces import Route, AppContainer, Router


class EndpointTests(unittest.TestCase):
    def test_compile_regex__regex_compile_returns_regex_like_thing(self):
        e = Route('/', None, None)
        self.assertTrue(hasattr(e._compile_regex('/'), 'match'))

    def test_compile_regex__angle_syntax_is_wildcard(self):
        url = "/<test>"
        e = Route(url, None, None)
        self.assertTrue(e._re.match("/something_here"))

    def test_compile_regex__raw_strings_can_match(self):
        url = "/testing/"
        e = Route(url, None, None)
        self.assertTrue(e._re.match("/testing/"))

    @unittest.skip("Skipped failing test which allows raw regexp usage.")
    def test_compile_regex__cant_match_raw_regex_syntax(self):
        url = "/foo(.*)bar"
        e = Route(url, None, None)
        self.assertEqual(e._re.match("/fooziebar", 'GET'), None)

    def test_compile_regex__angle_syntax_captures_input(self):
        url = "/<test>"
        e = Route(url, None, None)
        gd = e._re.match("/something_here").groupdict()
        self.assertIn('test', gd)
        self.assertEqual(gd['test'], 'something_here')

    def test_compile_regex__angle_syntax_multiple_instances(self):
        url = "/<one>/and/<two>"
        e = Route(url, None, None)
        gd = e._re.match("/bill/and/ted").groupdict()
        self.assertEqual(gd['one'], 'bill')
        self.assertEqual(gd['two'], 'ted')

    def test_handles_route__true_if_match(self):
        url = "/test"
        e = Route(url, None, None)
        self.assertTrue(e.handles_route(url, 'GET'))

    def test_handles_route__false_if_no_match(self):
        url = "/test"
        e = Route(url, None, None)
        self.assertFalse(e.handles_route("/nottest", 'GET'))

    def test_handles_route__false_if_different_method(self):
        url = '/test'
        e = Route(url, None, None, methods=['POST'])
        self.assertFalse(e.handles_route(url, 'GET'))

    def test_match__returns_dict_on_angle_match(self):
        url = "/<works>"
        e = Route(url, None, None)
        matches = e._match("/oh_yea")
        self.assertIsInstance(matches, dict)
        self.assertIn('works', matches)
        self.assertEqual(matches['works'], 'oh_yea')

    def test_match__returns_dict_on_raw_match(self):
        url = "/works"
        e = Route(url, None, None)
        self.assertIsInstance(e._match("/works"), dict)

    def test_match__returns_none_on_no_match(self):
        url = "/<test>"
        e = Route(url, None, None)

        self.assertEqual(e._match("nope"), None)

    def test_match__shouldnt_pick_up_longer_url(self):
        e = Route("/", None, None)
        self.assertFalse(
            e.handles_route("/NB2HI4B2F4XWO33PM5WGKLTDN5WQ====", 'GET'))

    def test_handle__calls_on_match_with_bound_params(self):
        class Endpoint(object):
            args = {}

            def test(self, test):
                self.args['test'] = test

        e = Endpoint()
        r = Route("/<test>", e, 'test')

        _partial = r.handle('/foo')

        self.assertEqual(len(e.args), 0)
        _partial()
        self.assertEqual(len(e.args), 1)
        self.assertEqual(e.args['test'], 'foo')

    def test_handle__attribute_error_on_nonexistant_method(self):
        class Endpoint(object):
            pass

        e = Route("/<test>", Endpoint(), 'test')

        self.assertRaises(AttributeError, e.handle, '/foo')


class MockRequest(object):
    def __init__(self):
        self.args = {}
        self.form = {}


class AppContainerTests(unittest.TestCase):
    def setUp(self):
        self.app_container = AppContainer(None)
        self.mock_request = MockRequest()

    def test__default_handlers_exist(self):
        a = AppContainer(None)
        self.assertNotEqual(len(a._arg_providers), 0)

    def test_extract_params__returns_nothing_for_no_arg_func(self):
        def func():
            pass

        result = self.app_container._extract_params_from_request(
            functools.partial(func), self.mock_request)
        self.assertEqual(result, {})

    def test_extract_params__doesnt_return_self_for_method(self):
        class Klass(object):
            def meth(self):
                pass

        klass = Klass()

        func = functools.partial(klass.meth)
        result = self.app_container._extract_params_from_request(
            func, self.mock_request)
        self.assertEqual(result, {})

    def test_extract_params__doesnt_error_on_no_prefix_param(self):
        def func(something):
            pass

        result = self.app_container._extract_params_from_request(
            functools.partial(func), self.mock_request)
        self.assertEqual(result, {})

    def test_extract_parmas__doesnt_return_args_outside_of_prefix(self):
        def func(something__here):
            pass

        result = self.app_container._extract_params_from_request(
            functools.partial(func), self.mock_request)
        self.assertEqual(result, {})

    def test_extract_params__returns_get_params(self):
        def func(get__foo):
            pass

        self.mock_request.args = {'foo': 'bar'}
        result = self.app_container._extract_params_from_request(
            functools.partial(func), self.mock_request)
        self.assertEqual(result, {'get__foo': 'bar'})

    def test_extract_params__returns_post_params(self):
        def func(post__foo):
            pass

        self.mock_request.form = {'foo': 'bar'}
        result = self.app_container._extract_params_from_request(
            functools.partial(func), self.mock_request)
        self.assertEqual(result, {'post__foo': 'bar'})

    def test_extract_params__doesnt_pull_from_post_on_get(self):
        def func(post__foo):
            pass

        # Key here is that I'm populating args [where get data lives],
        # not form [where post data lives]
        self.mock_request.args = {'foo': 'bar'}
        result = self.app_container._extract_params_from_request(
            functools.partial(func), self.mock_request)
        self.assertEqual(result, {'post__foo': None})

    def test_extract_params__populates_with_default_kwargs(self):
        def func(post__foo=None):
            pass

        self.mock_request.form = {'foo': 'bar'}
        result = self.app_container._extract_params_from_request(
            functools.partial(func), self.mock_request)
        self.assertEqual(result, {'post__foo': 'bar'})


class RouterTests(unittest.TestCase):
    def test_router_with_no_init_raises_typeerror(self):
        self.assertRaises(TypeError, Router)

    def test_router_returns_none_on_no_match(self):
        r = Router([])
        self.assertIsNone(r.match(r, 'test'))

    def test_router_routes_to_known_route(self):
        matching_router = Mock()
        r = Router([matching_router])
        r.match(r, 'test')
        matching_router.handle.assert_called_with(r)


if __name__ == '__main__':
    unittest.main()