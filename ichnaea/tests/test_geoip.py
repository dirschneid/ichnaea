import os.path
import tempfile

from ichnaea.constants import GEOIP_CITY_ACCURACY
from ichnaea import geoip
from ichnaea.geoip import radius_from_geoip
from ichnaea.tests.base import (
    LogIsolation,
    FREMONT_IP,
    TestCase,
)


class GeoIPBaseTest(LogIsolation):

    @classmethod
    def setUpClass(cls):
        super(GeoIPBaseTest, cls).setup_logging()

    @classmethod
    def tearDownClass(cls):
        super(GeoIPBaseTest, cls).teardown_logging()

    def setUp(self):
        self.clear_log_messages()

    @property
    def filename(self):
        return os.path.join(os.path.dirname(__file__), 'GeoIPCity.dat')

    def _open_db(self, path=None):
        if path is None:
            path = self.filename
        return geoip.configure_geoip(
            filename=path, heka_client=self.heka_client)


class TestDatabase(GeoIPBaseTest, TestCase):

    def test_open_ok(self):
        result = self._open_db()
        self.assertIsInstance(result, geoip.GeoIPWrapper)

    def test_open_missing_file(self):
        db = self._open_db('/i/taught/i/taw/a/putty/tat')
        self.assertTrue(isinstance(db, geoip.GeoIPNull))
        self.check_expected_heka_messages(
            sentry=[('msg', 'Error opening geoip database file.', 1)]
        )

    def test_open_invalid_file(self):
        with tempfile.NamedTemporaryFile() as temp:
            temp.write('Bucephalus')
            temp.seek(0)
            db = self._open_db(temp.name)
            self.assertTrue(isinstance(db, geoip.GeoIPNull))

        self.check_expected_heka_messages(
            sentry=[('msg', 'Error opening geoip database file.', 1)]
        )

    def test_ascii_country_names(self):
        # iterate over all the available country names and make sure
        # they are all ascii-only
        from pygeoip.const import COUNTRY_NAMES
        for country in COUNTRY_NAMES:
            self.assertEqual(str(country), country.decode('utf-8'))

    def test_invalid_countries(self):
        db = self._open_db()
        for code in ('A1', 'A2', 'EU'):
            self.assertTrue(code in db.invalid_countries)


class TestGeoIPLookup(GeoIPBaseTest, TestCase):

    def test_ok(self):
        expected = {
            'area_code': 510,
            'city': 'Fremont',
            'continent': 'NA',
            'country_code': 'US',
            'country_code3': 'USA',
            'country_name': 'United States',
            'dma_code': 807,
            'latitude': 37.5079,
            'longitude': -121.96,
            'metro_code': 'San Francisco, CA',
            'postal_code': '94538',
            'region_code': 'CA',
            'time_zone': 'America/Los_Angeles',
        }

        db = self._open_db()
        # Known good value in the wee sample DB we're using
        r = db.geoip_lookup(FREMONT_IP)
        for i in expected.keys():
            if i in ('latitude', 'longitude'):
                self.assertAlmostEqual(expected[i], r[i])
            else:
                self.assertEqual(expected[i], r[i])

    def test_fail(self):
        db = self._open_db()
        self.assertIsNone(db.geoip_lookup('127.0.0.1'))

    def test_fail_bad_ip(self):
        db = self._open_db()
        self.assertIsNone(db.geoip_lookup('546.839.319.-1'))

    def test_with_dummy_db(self):
        self.assertIsNone(geoip.GeoIPNull().geoip_lookup('200'))


class TestCountryLookup(GeoIPBaseTest, TestCase):

    def test_ok(self):
        db = self._open_db()
        # Known good value in the wee sample DB we're using
        code = db.country_lookup(FREMONT_IP)
        self.assertEqual(code, ('US', 'United States'))

    def test_fail(self):
        db = self._open_db()
        self.assertIsNone(db.country_lookup('127.0.0.1'))

    def test_fail_bad_ip(self):
        db = self._open_db()
        self.assertIsNone(db.country_lookup('546.839.319.-1'))

    def test_with_dummy_db(self):
        self.assertIsNone(geoip.GeoIPNull().country_lookup('200'))

    def test_invalid_country(self):
        db = self._open_db()
        db.invalid_countries = frozenset(['', 'US'])
        self.assertIsNone(db.country_lookup(FREMONT_IP))


class TestGuessRadius(TestCase):

    li_radius = 13000.0
    usa_radius = 2826000.0
    vat_radius = 1000.0

    def test_alpha2(self):
        a, c = radius_from_geoip({'country_code': 'US'})
        self.assertEqual(a, self.usa_radius)
        self.assertFalse(c)

    def test_alpha3(self):
        a, c = radius_from_geoip({'country_code3': 'USA'})
        self.assertEqual(a, self.usa_radius)
        self.assertFalse(c)

    def test_alpha3_takes_precedence(self):
        a, c = radius_from_geoip({'country_code3': 'USA',
                                  'country_code': 'LI'})
        self.assertEqual(a, self.usa_radius)
        self.assertFalse(c)

    def test_city(self):
        a, c = radius_from_geoip({'country_code3': 'USA',
                                  'city': 'Fremont'})
        self.assertEqual(a, GEOIP_CITY_ACCURACY)
        self.assertTrue(c)

    def test_small_country_alpha2(self):
        a, c = radius_from_geoip({'country_code': 'LI',
                                  'city': 'Vaduz'})
        self.assertEqual(a, self.li_radius)
        self.assertTrue(c)

    def test_small_country_alpha3(self):
        a, c = radius_from_geoip({'country_code3': 'VAT',
                                  'city': 'Vatican City'})
        self.assertEqual(a, self.vat_radius)
        self.assertTrue(c)
