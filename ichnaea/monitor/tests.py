from datetime import timedelta

from ichnaea.models import (
    ApiKey,
    CellMeasure,
    OCIDCell,
    RADIO_TYPE,
    WifiMeasure,
)
from ichnaea.monitor.tasks import (
    monitor_api_key_limits,
    monitor_measures,
    monitor_ocid_import,
    monitor_queue_length,
)
from ichnaea.tests.base import CeleryTestCase
from ichnaea import util


class TestMonitorTasks(CeleryTestCase):

    def test_monitor_api_key_limits_empty(self):
        result = monitor_api_key_limits.delay().get()
        self.assertEqual(result, {})

    def test_monitor_api_key_limits_one(self):
        redis_client = self.redis_client
        now = util.utcnow()
        today = now.strftime("%Y%m%d")

        key = "apilimit:no_key_1:" + today
        redis_client.incr(key, 13)

        result = monitor_api_key_limits.delay().get()
        self.assertEqual(result, {'no_key_1': 13})

        self.check_stats(
            gauge=['apilimit.no_key_1'],
        )

    def test_monitor_api_key_limits_multiple(self):
        redis_client = self.redis_client
        session = self.db_master_session
        now = util.utcnow()
        today = now.strftime("%Y%m%d")
        yesterday = (now - timedelta(hours=24)).strftime("%Y%m%d")
        data = {
            'test': 11,
            'no_key_1': 12,
            'no_key_2': 15,
        }
        for k, v in data.items():
            key = "apilimit:%s:%s" % (k, today)
            redis_client.incr(key, v)
            key = "apilimit:%s:%s" % (k, yesterday)
            redis_client.incr(key, v - 10)

        api_keys = [
            ApiKey(valid_key='no_key_1', shortname='shortname_1'),
            ApiKey(valid_key='no_key_2'),
            ApiKey(valid_key='no_key_3', shortname='shortname_3'),
        ]
        session.add_all(api_keys)
        session.flush()

        # add some other items into Redis
        redis_client.lpush('default', 1, 2)
        redis_client.set('cache_something', '{}')

        result = monitor_api_key_limits.delay().get()

        self.check_stats(
            gauge=['apilimit.test',
                   'apilimit.shortname_1',
                   'apilimit.no_key_2'],
        )
        self.assertDictEqual(
            result, {'test': 11, 'shortname_1': 12, 'no_key_2': 15})

    def test_monitor_measures(self):
        session = self.db_master_session

        result = monitor_measures.delay().get()
        self.check_stats(
            gauge=[('table.cell_measure', 1), ('table.wifi_measure', 1)],
        )
        self.assertEqual(result, {'cell_measure': -1, 'wifi_measure': -1})

        # add some measures
        session.add_all([CellMeasure() for i in range(3)])
        session.add_all([WifiMeasure() for i in range(5)])
        session.flush()

        result = monitor_measures.delay().get()
        self.check_stats(
            gauge=[('table.cell_measure', 2), ('table.wifi_measure', 2)],
        )
        self.assertEqual(result, {'cell_measure': 3, 'wifi_measure': 5})

    def test_monitor_ocid_import(self):
        session = self.db_master_session
        now = util.utcnow()
        cell_args = dict(radio=RADIO_TYPE['gsm'], mcc=262, mnc=1, lac=1)

        expected = []
        results = []
        for i in range(30, 0, -5):
            created = now - timedelta(hours=i)
            expected.append(i * 3600000)
            session.add(OCIDCell(created=created, cid=i, **cell_args))
            session.flush()
            results.append(monitor_ocid_import.delay().get())

        self.check_stats(
            gauge=[('table.ocid_cell_age', len(expected))],
        )
        for r, e in zip(results, expected):
            # The values should be almost equal, ignoring differences
            # less than 10 seconds (or 9999 milliseconds / 4 places)
            self.assertAlmostEqual(r, e, -4)

    def test_monitor_queue_length(self):
        data = {
            'celery_default': 2,
            'celery_incoming': 3,
            'celery_insert': 5,
            'celery_monitor': 1,
            'update_cell': 4,
            'update_cell_lac': 7,
            'update_wifi': 6,
        }
        for k, v in data.items():
            self.redis_client.lpush(k, *range(v))
        # BBB
        for name in ('default', 'incoming', 'insert', 'monitor'):
            data[name] = 0

        result = monitor_queue_length.delay().get()

        self.check_stats(
            gauge=['queue.' + k for k in data.keys()],
        )
        self.assertEqual(result, data)
