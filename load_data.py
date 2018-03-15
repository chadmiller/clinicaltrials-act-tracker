# -*- coding: utf-8 -*-
import logging
import traceback
import sys
import os
import subprocess
import json
import glob
import datetime
import tempfile
import shutil
import requests
import contextlib
import re
from zipfile import ZipFile
from csv import DictWriter
import multiprocessing
from time import time

import extraction


STORAGE_PREFIX = 'clinicaltrials-data/'
WORKING_VOLUME = os.environ.get('DATA_DIR', '/mnt/volume-lon1-01/')   # location with at least 10GB space
WORKING_DIR = os.path.join(WORKING_VOLUME, STORAGE_PREFIX)


def document_stream(zip_filename):
    logging.debug("Beginning incremental extraction of %s", zip_filename)
    with open(zip_filename, 'rb') as z:
        with ZipFile(z) as enormous_zipfile:
            for name in enormous_zipfile.namelist():
                if "NCT" not in name or not name.endswith(".xml"):
                    continue
                yield name, enormous_zipfile.read(name)


def fabricate_csv(input_filename, output_filename):
    _, temp_output_filename = tempfile.mkstemp()

    pool = multiprocessing.Pool()

    columns = [
            'nct_id', 'act_flag', 'included_pact_flag', 'location', 'exported', 'phase', 'start_date', 'available_completion_date', 'legacy_fda_regulated', 'primary_completion_date_used', 'has_results', 'results_submitted_date', 'has_certificate', 'certificate_date', 'results_due', 'study_status', 'study_type', 'primary_purpose', 'fda_reg_drug', 'fda_reg_device', 'sponsor', 'sponsor_type', 'url', 'title', 'condition', 'condition_mesh', 'intervention', 'intervention_mesh',

            'brief_title', 'collaborators', 'defaulted_cd_flag', 'defaulted_date', 'defaulted_pcd_flag', 'discrep_date_status', 'late_cert', 'official_title', ]
    with open(temp_output_filename, 'w') as out:
        csv = DictWriter(out, columns)
        csv.writeheader()

        def result_callback(row):
            if row:
                csv.writerow(row)

        def error_callback(exception):
            logging.exception("Couldn't get data from %s.", name, exception=exception)

        for name, xmldoc in document_stream(input_filename):
            pool.apply_async(extraction.document_to_record, (xmldoc, name), callback=result_callback, error_callback=error_callback)
        pool.close()
        pool.join()

    os.rename(temp_output_filename, output_filename)


def download_and_extract():
    """If file is more than 20 hours old, download into a temp location and
    move the result into place.

    We can't extract as we download (bah!) because ZIP format places its index
    at the end of the file.
    """
    url = 'https://clinicaltrials.gov/AllPublicXML.zip'
    destination = os.path.join(WORKING_DIR, "clinicaltrialsgov-allxml.zip")
    if not os.path.exists(destination) or os.path.getmtime(destination) < (time() - 72000):
        _, download_temp = tempfile.mkstemp(prefix="clinicaltrialsgovzip", dir=WORKING_DIR)
        logging.info("Downloading %s to %s. This may take some time.", url, download_temp)
        subprocess.check_call(["wget", "--no-use-server-timestamps", "--quiet", "-O", download_temp, url])
        logging.info("Finished downloading %s and saving as %s", url, destination)
        os.rename(download_temp, destination)
    else:
        logging.info("Discovered fresh %s", destination)
    return destination


def notify_slack(message):
    """Posts the message to #general
    """
    # Set the webhook_url to the one provided by Slack when you create
    # the webhook at
    # https://my.slack.com/services/new/incoming-webhook/
    webhook_url = os.environ['SLACK_GENERAL_POST_KEY']
    slack_data = {'text': message}

    response = requests.post(webhook_url, json=slack_data)
    if response.status_code != 200:
        raise ValueError(
            'Request to slack returned an error %s, the response is:\n%s'
            % (response.status_code, response.text)
        )


if __name__ == '__main__':
    logging.basicConfig(
            filename=os.path.join(WORKING_VOLUME, 'data_load.log'),
            format="%(asctime)s %(filename)s:%(lineno)s %(message)s", level=logging.DEBUG)
    try:
        enormous_zipfile = download_and_extract()
        fabricate_csv(enormous_zipfile, '/tmp/clinical_trials.csv')

        env = os.environ.copy()
        with open(os.environ.get("UPLOAD_SETTINGS", "/etc/profile.d/fdaaa_staging.sh")) as e:
            for k, _, v in re.findall(r"""^\s+export\s+([A-Z][A-Z0-9_]*)=([\"']?)(\S+|.*)\2""", e.read(), re.MULTILINE):
                env[k] = v
        subprocess.check_call(["/var/www/fdaaa_staging/venv/bin/python", "/var/www/fdaaa_staging/clinicaltrials-act-tracker/clinicaltrials/manage.py", "process_data", "--input-csv=/tmp/clinical_trials.csv", "--settings=frontend.settings"], env=env)
        notify_slack("""Today's data uploaded to FDAAA staging: https://staging-fdaaa.ebmdatalab.net.  If this looks good, tell ebmbot to 'update fdaaa staging'""")
    except:
        notify_slack("Error in FDAAA import: {}".format(traceback.format_exc()))
        raise
