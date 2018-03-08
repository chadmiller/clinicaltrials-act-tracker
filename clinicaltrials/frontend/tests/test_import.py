from datetime import date
from unittest import mock
import os

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from frontend.models import Ranking
from frontend.models import Trial

from frontend.trial_computer import qa_start_date


class DummyResponse(object):
    def __init__(self, content):
        self.content = content
        self.text = str(content)

def dummy_ccgov_results(url):
    sample_results = os.path.join(
        settings.BASE_DIR, 'frontend/tests/fixtures/results_with_qa.html')
    if url.endswith('overdueinqa'):
        with open(sample_results, 'r') as dummy_response:
            return DummyResponse(dummy_response.read())
    return DummyResponse('<html></html>')


class CommandsTestCase(TestCase):

    @mock.patch('requests.get', mock.Mock(side_effect=dummy_ccgov_results))
    @mock.patch('frontend.trial_computer.date')
    def test_import(self, datetime_mock):
        " Test my custom command."
        datetime_mock.today = mock.Mock(return_value=date(2018,1,1))

        args = []
        sample_csv = os.path.join(settings.BASE_DIR, 'frontend/tests/fixtures/sample_bq.csv')
        opts = {'input_csv': sample_csv}
        call_command('process_data', *args, **opts)

        reported = Trial.objects.get(registry_id='reported')
        self.assertEqual(reported.status, 'reported')
        self.assertEqual(reported.days_late, None)

        ongoing = Trial.objects.get(registry_id='ongoing')
        self.assertEqual(ongoing.status, 'ongoing')
        self.assertEqual(ongoing.days_late, None)

        overdue = Trial.objects.get(registry_id='overdue')
        self.assertEqual(overdue.status, 'overdue')
        self.assertEqual(overdue.days_late, 61)

        overdueinqa = Trial.objects.get(registry_id='overdueinqa')
        self.assertEqual(overdueinqa.status, 'reported-late')
        self.assertEqual(overdueinqa.days_late, 12)
        self.assertEqual(qa_start_date(overdueinqa), date(2017,11,13))

        late_sponsor_ranking = Ranking.objects.filter(sponsor=overdueinqa.sponsor).first()
        self.assertEqual(late_sponsor_ranking.days_late, 73)
        self.assertEqual(late_sponsor_ranking.finable_days_late, 31)

        self.assertEqual(Ranking.objects.first().days_late, None)
        self.assertEqual(Ranking.objects.first().finable_days_late, None)

        overdueingrace = Trial.objects.get(registry_id='overdueingrace')
        self.assertEqual(overdueingrace.status, 'ongoing')
        self.assertEqual(overdueingrace.days_late, None)

        self.assertEqual(Ranking.objects.first().sponsor, reported.sponsor)
        self.assertEqual(Ranking.objects.count(), 3)


    @mock.patch('requests.get', mock.Mock(side_effect=dummy_ccgov_results))
    @mock.patch('frontend.trial_computer.date')
    @mock.patch('frontend.management.commands.process_data.date')

    def test_second_import(self, mock_date_1, mock_date_2):
        ""
        mock_date_1.today = mock.Mock(return_value=date(2018,1,1))
        mock_date_2.today = mock.Mock(return_value=date(2018,1,1))

        args = []
        sample_csv = os.path.join(settings.BASE_DIR, 'frontend/tests/fixtures/sample_bq.csv')
        opts = {'input_csv': sample_csv}
        call_command('process_data', *args, **opts)

        overdue = Trial.objects.get(registry_id='overdue')
        self.assertEqual(overdue.status, 'overdue')
        self.assertEqual(overdue.days_late, 61)
        # Pretend the previous import took place ages ago
        Trial.objects.all().update(updated_date=date(2017,1,1))

        # Import again
        mock_date_1.today = mock.Mock(return_value=date(2018,1,2))
        mock_date_2.today = mock.Mock(return_value=date(2018,1,2))
        call_command('process_data', *args, **opts)

        overdue = Trial.objects.get(registry_id='overdue')
        self.assertEqual(overdue.status, 'overdue')
        self.assertEqual(overdue.days_late, 62)

        self.assertEqual(overdue.updated_date, date(2018,1,2))
        self.assertEqual(overdue.first_seen_date, date(2018,1,1))

    @mock.patch('requests.get', mock.Mock(side_effect=dummy_ccgov_results))
    @mock.patch('frontend.models.date')
    def test_second_import_with_disappeared_trials(self, datetime_mock):
        " Test my custom command."
        datetime_mock.today = mock.Mock(return_value=date(2018,1,1))

        args = []
        sample_csv = os.path.join(settings.BASE_DIR, 'frontend/tests/fixtures/sample_bq.csv')
        opts = {'input_csv': sample_csv}
        call_command('process_data', *args, **opts)

        # Pretend the previous import took place ages ago

        Trial.objects.all().update(updated_date=date(2017,1,1))

        # Import empty file
        sample_csv = os.path.join(settings.BASE_DIR, 'frontend/tests/fixtures/sample_bq_empty.csv')
        opts = {'input_csv': sample_csv}
        call_command('process_data', *args, **opts)

        # There should be no Trials visible
        self.assertEqual(Trial.objects.count(), 6)
        self.assertEqual(Trial.objects.visible().count(), 0)
