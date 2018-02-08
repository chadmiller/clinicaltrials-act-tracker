from django.test import TestCase
from django.core.exceptions import ValidationError
from datetime import date
from datetime import timedelta

from frontend.models import Sponsor
from frontend.models import Trial
from frontend.models import TrialQA
from frontend.models import Ranking

from unittest.mock import patch, Mock


trial_counter = 0
def _makeTrial(sponsor, **kw):
    global trial_counter
    tomorrow = date.today() + timedelta(days=1)
    trial_counter += 1
    defaults = {
        'sponsor': sponsor,
        'start_date': date(2015, 1, 1),
        'completion_date': date(2016, 1, 1),
        'registry_id': 'id_{}'.format(trial_counter),
        'publication_url': 'http://bar.com/{}'.format(trial_counter),
        'title': 'Trial {}'.format(trial_counter)
    }
    defaults.update(kw)
    trial = Trial.objects.create(**defaults)
    trial.compute_metadata()
    return trial

def _simulateImport(test_trials):
    """Do the same as the import script, but for an array of tuples
    """
    last_date = None
    for updated_date, sponsor, due, reported in test_trials:
        if updated_date != last_date:
            # simulate a new import; this means deleting all
            # existing Trials and updating rankings (see below)
            Ranking.objects.set_current()
            Trial.objects.all().delete()
        sponsor.updated_date = updated_date
        sponsor.save()
        _makeTrial(
            sponsor,
            results_due=due,
            has_results=reported,
            reported_date=updated_date
        )
        last_date = updated_date
    Ranking.objects.set_current()


class RankingTestCase(TestCase):
    def setUp(self):
        self.date1 = date(2016, 1, 1)
        self.date2 = date(2016, 2, 1)
        self.date3 = date(2016, 3, 1)
        self.sponsor1 = Sponsor.objects.create(name="Sponsor 1")
        self.sponsor2 = Sponsor.objects.create(name="Sponsor 2")
        self.sponsor3 = Sponsor.objects.create(name="Sponsor 3")

        test_trials = [
            # date,  sponsor, due, reported
            (self.date1, self.sponsor1, True, False),
            (self.date1, self.sponsor2, True, True),
            (self.date1, self.sponsor2, True, True),

            (self.date2, self.sponsor1, True, False),
            (self.date2, self.sponsor1, True, True),
            (self.date2, self.sponsor2, True, False),
            (self.date2, self.sponsor2, True, False),

            (self.date3, self.sponsor2, True, True),
            (self.date3, self.sponsor2, True, True),
            (self.date3, self.sponsor1, True, True),
            (self.date3, self.sponsor1, True, True),
        ]
        _simulateImport(test_trials)

    def test_percentage_set(self):
        self.assertEqual(self.sponsor1.rankings.get(date=self.date1).percentage, 0.0)
        self.assertEqual(self.sponsor1.rankings.get(date=self.date2).percentage, 50.0)
        self.assertEqual(self.sponsor1.rankings.get(date=self.date3).percentage, 100.0)
        self.assertEqual(self.sponsor2.rankings.get(date=self.date1).percentage, 100.0)
        self.assertEqual(self.sponsor2.rankings.get(date=self.date2).percentage, 0.0)
        self.assertEqual(self.sponsor2.rankings.get(date=self.date3).percentage, 100.0)

    def test_compute_ranks(self):
        ranks = Ranking.objects.with_rank().filter(date=self.date1).all()
        self.assertEqual(ranks[0].rank, 1)
        self.assertEqual(ranks[0].sponsor, self.sponsor2)
        self.assertEqual(ranks[1].rank, 2)
        self.assertEqual(ranks[1].sponsor, self.sponsor1)

        ranks = Ranking.objects.with_rank().filter(date=self.date2).all()
        self.assertEqual(ranks[0].rank, 1)
        self.assertEqual(ranks[0].sponsor, self.sponsor1)
        self.assertEqual(ranks[1].rank, 2)
        self.assertEqual(ranks[1].sponsor, self.sponsor2)

        ranks = Ranking.objects.with_rank().filter(date=self.date3).all()
        self.assertEqual(ranks[0].rank, 1)
        self.assertEqual(ranks[0].sponsor, self.sponsor1)
        self.assertEqual(ranks[1].rank, 1)
        self.assertEqual(ranks[1].sponsor, self.sponsor2)


class SponsorTrialsTestCase(TestCase):
    def setUp(self):
        self.sponsor = Sponsor.objects.create(name="Sponsor 1")
        self.sponsor2 = Sponsor.objects.create(name="Sponsor 2")
        self.due_trial = _makeTrial(
            self.sponsor,
            results_due=True,
            has_results=False)
        self.reported_trial = _makeTrial(
            self.sponsor,
            results_due=True,
            has_results=True,
            reported_date=date(2016,12,1))
        self.not_due_trial = _makeTrial(
            self.sponsor,
            results_due=False,
            has_results=False)

    def test_slug(self):
        self.assertEqual(self.sponsor.slug, 'sponsor-1')

    def test_zombie_sponsor(self):
        self.assertEqual(len(self.sponsor.trials().all()), 3)
        due = self.due_trial
        due.no_longer_on_website = True
        due.save()
        self.assertEqual(len(self.sponsor.trials().all()), 2)

    def test_trials_due(self):
        self.assertEqual(
            list(self.sponsor.trials().due()),
            [self.reported_trial, self.due_trial])

    def test_trials_unreported(self):
        self.assertEqual(
            list(self.sponsor.trials().unreported()),
            [self.not_due_trial, self.due_trial])
        self.assertEqual(self.not_due_trial.status, 'ongoing')

    def test_trials_reported(self):
        self.assertEqual(
            list(self.sponsor.trials().reported()),
            [self.reported_trial])

    def test_trials_overdue(self):
        self.assertEqual(self.due_trial.status, 'overdue')
        self.assertEqual(
            list(self.sponsor.trials().overdue()),
            [self.due_trial])

    def test_trials_reported_early(self):
        self.assertEqual(
            list(self.sponsor.trials().reported_early()),
            [])

class SponsorTrialsStatusTestCase(TestCase):
    def setUp(self):
        self.sponsor = Sponsor.objects.create(name="Sponsor 1")

    def test_trial_overdue(self):
        trial = _makeTrial(
            self.sponsor,
            has_results=False,
            results_due=True,
            completion_date='2016-01-01')
        self.assertEqual(trial.status, 'overdue')
        self.assertEqual(
            list(self.sponsor.trials().overdue()),
            [trial])

    def test_trial_ongoing(self):
        trial = _makeTrial(
            self.sponsor,
            has_results=False,
            results_due=False,
            completion_date='2016-01-01')
        self.assertEqual(trial.status, 'ongoing')

    def test_trial_not_reported_late(self):
        trial = _makeTrial(
            self.sponsor,
            has_results=True,
            results_due=True,
            completion_date='2016-01-01',
            reported_date= '2016-12-01')
        self.assertEqual(trial.status, 'reported')
        self.assertEqual(
            list(self.sponsor.trials().reported_late()),
            [])

    def test_trial_under_qa(self):
        trial = _makeTrial(
            self.sponsor,
            has_results=False,
            results_due=True,
            completion_date='2016-01-01')
        TrialQA.objects.create(
            submitted_to_regulator='2016-02-01',
            returned_to_sponsor=None,
            trial=trial
        )
        trial.compute_metadata()
        self.assertEqual(trial.status, 'qa')

    def test_trials_reported_late_is_late(self):
        trial = _makeTrial(
            self.sponsor,
            has_results=True,
            results_due=True,
            completion_date='2016-01-01',
            reported_date= '2017-01-01')
        self.assertEqual(trial.status, 'reported-late')
        self.assertEqual(
            list(self.sponsor.trials().reported_late()),
            [trial])


class SponsorTrialsLatenessTestCase(TestCase):
    def setUp(self):
        self.sponsor = Sponsor.objects.create(name="Sponsor 1")

    def test_reported_trial_late(self):
        trial = _makeTrial(
            self.sponsor,
            has_results=True,
            results_due=True,
            completion_date='2016-01-01',
            reported_date= '2017-01-01')
        self.assertEqual(trial.days_late, 1)

    def test_reported_trial_not_late(self):
        trial = _makeTrial(
            self.sponsor,
            has_results=True,
            results_due=True,
            completion_date='2016-01-01',
            reported_date= '2016-12-01')
        self.assertEqual(trial.days_late, 0)

    def test_trial_under_qa_not_late(self):
        trial = _makeTrial(
            self.sponsor,
            has_results=False,
            results_due=True,
            completion_date='2016-01-01')
        TrialQA.objects.create(
            submitted_to_regulator='2016-02-01',
            returned_to_sponsor=None,
            trial=trial
        )
        trial.compute_metadata()
        self.assertEqual(trial.days_late, 0)

    def test_trial_under_qa_late(self):
        trial = _makeTrial(
            self.sponsor,
            has_results=False,
            results_due=True,
            completion_date='2016-01-01')
        TrialQA.objects.create(
            submitted_to_regulator='2017-01-01',
            returned_to_sponsor=None,
            trial=trial
        )
        trial.compute_metadata()
        self.assertEqual(trial.days_late, 1)

    @patch('frontend.models.date')
    def test_unreported_trial_late_within_grace(self, datetime_mock):
        datetime_mock.today = Mock(return_value=date(2017,1,30))
        trial = _makeTrial(
            self.sponsor,
            has_results=False,
            results_due=True,
            completion_date='2016-01-01')
        self.assertEqual(trial.days_late, 0)

    @patch('frontend.models.date')
    def test_unreported_trial_late_outside_grace(self, datetime_mock):
        datetime_mock.today = Mock(return_value=date(2017,1,31))
        trial = _makeTrial(
            self.sponsor,
            has_results=False,
            results_due=True,
            completion_date='2016-01-01')
        self.assertEqual(trial.days_late, 31)
