
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta
import xml.etree.ElementTree as ET


def st(node):
    """Safely strip strings but leave Nones alone."""
    if node is None: return None
    removed = None
    return node.text.strip(removed)


def first_date(r, paths):
    """Render the first-nonnull value to a date, conservatively making day-less
    months into end-of-month dates."""
    # TODO(chad): Fancy date math is unnecessary. Change all date handling to string handling and compare dates lexically. Worth 10 sec.
    for path in paths:
        val = r.find(path)
        if val is None: continue
        try:
            d = datetime.strptime(val.text.strip(), "%B %d, %Y")
            is_exact = True
        except ValueError:
            # No day, so push to end of that month.
            d = datetime.strptime(val.text.strip(), "%B %Y").replace(day=1) + relativedelta(months=+1) + relativedelta(days=-1)
            is_exact = False
        return d, is_exact
    return None, None


def document_to_record(xml_bytes):
    r = ET.fromstring(xml_bytes)
    d = {}

    phase = st(r.find("phase"))
    if not phase in ('Phase 1/Phase 2', 'Phase 2', 'Phase 2/Phase 3', 'Phase 3', 'Phase 4', 'N/A'): return

    study_status = st(r.find("overall_status"))
    if not study_status != 'Withdrawn': return

    primary_purpose = st(r.find("study_design_info/primary_purpose"))
    if not primary_purpose != 'Device Feasibility': return

    now = datetime.now()

    study_type = st(r.find("study_type"))
    start_date, _ = first_date(r, ["start_date"])
    fda_reg_drug = st(r.find("oversight_info/is_fda_regulated_drug"))
    fda_reg_device = st(r.find("oversight_info/is_fda_regulated_device"))
    primary_completion_date, primary_completion_date_is_exact = first_date(r, ["primary_completion_date"])
    completion_date, completion_date_is_exact = first_date(r, ["completion_date"])
    available_completion_date = primary_completion_date or completion_date
    intervention = st(r.find("intervention"))

    is_fda_regulated = fda_reg_drug == "Yes" or fda_reg_device == "Yes"   # Probably wrong.

    if study_type == 'Interventional' and \
            (fda_reg_drug == 'Yes' or fda_reg_device == 'Yes') and \
            primary_purpose != 'Device Feasibility' and \
            start_date is not None and start_date >= datetime(year=2017, month=1, day=18):
        act_flag = 1
    else:
        act_flag = 0

    if study_type == 'Interventional' and \
            intervention and re.search(r"Biological|Drug|Device|Genetic|Radiation", intervention) and \
            available_completion_date >= datetime(year=2017, month=1, day=18) and \
            start_date < datetime(year=2017, month=1, day=18) and \
            ((fda_reg_drug == 'Yes' or fda_reg_device == 'Yes') or (is_fda_regulated and fda_reg_drug is None and fda_reg_device is None)) and \
            location and re.search(r"\b(?:United States|American Samoa|Guam|Northern Mariana Islands|Puerto Rico|U\.S\. Virgin Islands)\b", location):
        included_pact_flag = 1
    else:
        included_pact_flag = 0

    if included_pact_flag != 1 and act_flag != 1: return

    certificate_date, _ = first_date(r, ["disposition_first_submitted"])
    has_results = int(r.find("clinical_results") is not None)

    official_title = st(r.find("official_title")) 
    brief_title = st(r.find("brief_title"))

    if (primary_completion_date is None or primary_completion_date < now) and \
            completion_date < now and \
            study_status in {'Not yet recruiting', 'Active, not recruiting', 'Recruiting', 'Enrolling by invitation', 'Unknown status', 'Available', 'Suspended'}:
        discrep_date_status = 1
    else:
        discrep_date_status = 0

    collaborators = " / ".join("{0}={1}".format(i.find("agency").text, i.find("agency_class").text.replace("=", " eq ")) for i in r.findall("sponsors/lead_sponsor")+r.findall("sponsors/collaborator"))
    

    d["nct_id"] = st(r.find("id_info/nct_id"))
    d["act_flag"] = act_flag
    d["included_pact_flag"] = included_pact_flag
    d["location"] = st(r.find("location"))
    d["exported"] = st(r.find("oversight_info/is_us_export"))
    d["phase"] = phase
    d["start_date"] = start_date.strftime("%Y-%m-%d")
    d["available_completion_date"] = available_completion_date.strftime("%Y-%m-%d")
    d["legacy_fda_regulated"] = int(is_fda_regulated)
    d["primary_completion_date_used"] = int(primary_completion_date is not None)
    d["has_results"] = has_results
    d["results_submitted_date"], _ = first_date(r, ["results_first_submitted"])
    d["has_certificate"] = int(certificate_date is not None)
    d["certificate_date"] = certificate_date
    d["results_due"] = int(certificate_date is None or certificate_date + relativedelta(years=3, days=30) > now)

    d["primary_completion_date_used"] = int(primary_completion_date is not None)
    d["defaulted_pcd_flag"] = int(primary_completion_date_is_exact == False)
    d["defaulted_cd_flag"] = int(completion_date_is_exact == False)
    #last_updated_date, --The last date the trial record was updated
    d["defaulted_cd_flag"] = st(r.find("enrollment"))
    d["study_status"] = st(r.find("overall_status"))
    d["study_type"] = study_type
    d["collaborators"] = collaborators
    d["primary_purpose"] = primary_purpose
    d["sponsor"] = st(r.find("sponsors/lead_sponsor/agency"))
    d["sponsor_type"] = st(r.find("sponsors/lead_sponsor.agency_class"))

    d["fda_reg_drug"] = fda_reg_drug
    d["fda_reg_device"] = fda_reg_device

    d["url"] = st(r.find("required_header/url"))
    d["title"] = official_title or brief_title
    d["official_title"] = official_title
    d["brief_title"] = brief_title

    d["discrep_date_status"] = discrep_date_status
    d["late_cert"] = int(certificate_date is not None and available_completion_date is not None and certificate_date > available_completion_date + relativedelta(years=1))

    d["defaulted_date"] = not primary_completion_date_is_exact or not completion_date_is_exact

    d["condition"] = st(r.find("condition"))
    d["condition_mesh"] = st(r.find("condition_browse"))
    d["intervention"] = intervention
    d["intervention_mesh"] = st(r.find("intervention_browse"))

    return d
