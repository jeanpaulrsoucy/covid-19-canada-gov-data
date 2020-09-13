# import modules
import sys
import time
import os
from shutil import copyfile
from datetime import datetime, timedelta
import json
import pandas as pd
import pytz
from git import Repo
import requests
import tempfile
from selenium import webdriver # requires ChromeDriver and Chromium/Chrome
from selenium.webdriver.chrome.options import Options
from colorit import *

# allow script to be run in testing mode (no commits written)
if len(sys.argv) == 1:
        mode = 'prod' # writing files on server
elif len(sys.argv) == 2 and sys.argv[1] == 'localprod':
        mode = 'localprod' # writing files on local machine
elif len(sys.argv) == 2 and sys.argv[1] == 'test':
        mode = 'test' # testing on server
elif len(sys.argv) == 2 and sys.argv[1] == 'localtest':
        mode = 'localtest' # testing on local machine
else:
        sys.exit("Error: Invalid arguments.")

# print with colour
init_colorit()

# define date in America/Toronto time zone
t = datetime.now(pytz.timezone('America/Toronto'))

# access repo
if mode == 'prod' or mode == 'localprod':
        ## access token
        if mode == 'prod':
                token = os.environ['GH_TOKEN']
                gh_name = os.environ['GH_NAME']
                gh_mail = os.environ['GH_MAIL']
        elif mode == 'localprod':
                token = open('.gh/token.txt', 'r').readline().rstrip()
                gh_name = open('.gh/gh_name.txt', 'r').readline().rstrip()
                gh_mail = open('.gh/gh_mail.txt', 'r').readline().rstrip()
        ## set repository directory
        repo_dir = 'temp_archive'
        ## shallow clone
        repo_remote = 'https://' + token + ':x-oauth-basic@github.com/jeanpaulrsoucy/covid-19-canada-gov-data'
        repo = Repo.clone_from(repo_remote, repo_dir, depth=1)
        origin = repo.remote('origin')
        ### set identity
        repo.config_writer().set_value("user", "name", gh_name).release()
        repo.config_writer().set_value("user", "email", gh_mail).release()
        ## initialize file list
        file_list = []
        ## initialize commit message
        commit_message = 'Nightly update: ' + str(t.date()) + '\n\n'

# function: prepare file(s) for commit
def prep_files(name, full_name, data = None, fpath=None, copy=False):
        global commit_message
        spath = os.path.join(repo_dir, full_name)
        os.makedirs(os.path.dirname(spath), exist_ok=True)
        if copy:
                copyfile(fpath, spath)
        else:
                with open(spath, mode='wb') as local_file:
                        local_file.write(data)
        file_list.append(full_name)
        commit_message = commit_message + 'Success: ' + full_name + '\n'
        print(color('Copy successful: ' + full_name, Colors.blue))

# function: commit files
def commit_files(file_list, commit_message):
        repo.index.add(file_list)
        repo.index.commit(commit_message)
        origin.push()

# function: download and commit file
def dl_file(url, path, file, user=False, ext='.csv', mb_json_to_csv=None):
        global commit_message
        if user == True:
                headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:66.0) Gecko/20100101 Firefox/66.0"}
                req = requests.get(url, headers=headers)
        else:
                req = requests.get(url)
        name = file + '_' + datetime.now(pytz.timezone('America/Toronto')).strftime('%Y-%m-%d_%H-%M')
        full_name = os.path.join(path, name + ext)
        if not req.ok:
                print(background('Error downloading: ' + full_name, Colors.red))
                if mode == 'prod' or mode == 'localprod':
                        commit_message = commit_message + 'Failure: ' + full_name + '\n'
        elif mode != 'prod' and mode != 'localprod':
                print(color('Test download successful: ' + full_name, Colors.green))
        else:
                if mb_json_to_csv:
                        name = file + '_' + datetime.now(pytz.timezone('America/Toronto')).strftime('%Y-%m-%d_%H-%M')
                        full_name = os.path.join(path, name + ext)                          
                        tmpdir = tempfile.TemporaryDirectory()
                        fpath = os.path.join(tmpdir.name, file + ext)
                        data = pd.json_normalize(json.loads(req.content)['features'])
                        data.columns = data.columns.str.lstrip('attributes.') # strip prefix
                        # replace timestamps with actual dates
                        data.Date = pd.to_datetime(data.Date / 1000, unit='s').dt.date
                        data = data.to_csv(fpath, index=None)
                        prep_files(name=name, full_name=full_name, fpath=fpath, copy=True)
                else:
                        data = req.content
                        prep_files(name=name, full_name=full_name, data=data)

# function: download and commit csv from AB - "COVID-19 Alberta statistics"
def dl_ab_cases(url, path, file, ext='.csv', wait=5):
        global commit_message
        
        ## set names
        name = file + '_' + datetime.now(pytz.timezone('America/Toronto')).strftime('%Y-%m-%d_%H-%M')
        full_name = os.path.join(path, name + ext)           
        
        ## create temporary directory
        tmpdir = tempfile.TemporaryDirectory()
        
        ## setup webdriver
        options = Options()
        if mode == 'prod' or mode == 'test':
                options.binary_location = os.environ['GOOGLE_CHROME_BIN']
        options.add_argument("--headless")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        prefs = {'download.default_directory' : tmpdir.name}
        options.add_experimental_option('prefs', prefs)
        if mode == 'prod' or mode == 'test':
                driver = webdriver.Chrome(executable_path=os.environ['CHROMEDRIVER_PATH'], options=options)
        else:
                driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(10)
        
        ## click to export
        driver.get(url)
        elements = driver.find_elements_by_tag_name("li")
        for element in elements:
                if element.text == 'Data export':
                        element.click()
        elements = driver.find_elements_by_tag_name("button")
        for element in elements:
                if element.text == 'CSV':
                        element.click()
        
        ## verify download
        fpath = os.path.join(tmpdir.name, file + ext)
        time.sleep(wait) # wait for download to finish
        
        ## commit file
        if not os.path.isfile(fpath):
                print(background('Error downloading: ' + full_name, Colors.red))
                if mode == 'prod' or mode == 'localprod':
                        commit_message = commit_message + 'Failure: ' + full_name + '\n'                
        elif mode != 'prod' and mode != 'localprod':
                print(color('Test download successful: ' + full_name, Colors.green))
        else:
                prep_files(name=name, full_name=full_name, fpath=fpath, copy=True)

# function: download and commit csv from AB - "COVID-19 relaunch status map" or AB - "COVID-19 school status map"
def dl_ab_oneclick(url, path, file, ext='.csv', wait=5):
        global commit_message
        
        ## set names
        name = file + '_' + datetime.now(pytz.timezone('America/Toronto')).strftime('%Y-%m-%d_%H-%M')
        full_name = os.path.join(path, name + ext)        
        
        ## create temporary directory
        tmpdir = tempfile.TemporaryDirectory()
        
        ## setup webdriver
        options = Options()
        if mode == 'prod' or mode == 'test':
                options.binary_location = os.environ['GOOGLE_CHROME_BIN']
        options.add_argument("--headless")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        prefs = {'download.default_directory' : tmpdir.name}
        options.add_experimental_option('prefs', prefs)
        if mode == 'prod' or mode == 'test':
                driver = webdriver.Chrome(executable_path=os.environ['CHROMEDRIVER_PATH'], options=options)
        else:
                driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(10)
        
        ## click to export
        driver.get(url)
        elements = driver.find_elements_by_tag_name("button")
        for element in elements:
                if element.text == 'CSV':
                        element.click()
                        
        ## verify download
        fpath = os.path.join(tmpdir.name, file + ext)
        time.sleep(wait) # wait for download to finish

        ## commit file
        if not os.path.isfile(fpath):
                print(background('Error downloading: ' + full_name, Colors.red))
                if mode == 'prod' or mode == 'localprod':
                        commit_message = commit_message + 'Failure: ' + full_name + '\n'                
        elif mode != 'prod' and mode != 'localprod':
                print(color('Test download successful: ' + full_name, Colors.green))
        else:
                prep_files(name=name, full_name=full_name, fpath=fpath, copy=True)

# AB - COVID-19 Alberta statistics
dl_ab_cases('https://www.alberta.ca/stats/covid-19-alberta-statistics.htm',
            'ab/cases/',
            'covid19dataexport')

# AB - COVID-19 relaunch status map
dl_ab_oneclick('https://www.alberta.ca/maps/covid-19-status-map.htm',
               'ab/active-cases-by-region/',
               'covid19dataexport-relaunch')

# AB - COVID-19 school status map
dl_ab_oneclick('https://www.alberta.ca/schools/covid-19-school-status-map.htm',
               'ab/school-status-by-region/',
               'covid19dataexport-schools')

# AB - COVID-19 in Alberta: Current cases by local geographic area (Edmonton)
dl_file('https://data.edmonton.ca/api/views/ix8f-s9xp/rows.csv?accessType=DOWNLOAD',
        'ab/edmonton-cases-by-area/',
        'COVID-19_in_Alberta__Current_cases_by_local_geographic_area')

# BC - BC COVID-19 Data (Case data)
dl_file('http://www.bccdc.ca/Health-Info-Site/Documents/BCCDC_COVID19_Dashboard_Case_Details.csv',
        'bc/case-data/',
        'BCCDC_COVID19_Dashboard_Case_Details')

# BC - BC COVID-19 Data (Laboratory data)
dl_file('http://www.bccdc.ca/Health-Info-Site/Documents/BCCDC_COVID19_Dashboard_Lab_Information.csv',
        'bc/laboratory-data/',
        'BCCDC_COVID19_Dashboard_Lab_Information')

# CAN - COVID-19 Situational Awareness Dashboard (Epidemiology update)
dl_file('https://health-infobase.canada.ca/src/data/covidLive/covid19.csv',
        'can/epidemiology-update/',
        'covid19')

# CAN - COVID-19 Situational Awareness Dashboard (Epidemiology summary statements)
dl_file('https://health-infobase.canada.ca/src/data/covidLive/covid19-epiSummary-statements.csv',
        'can/epidemiology-summary-statements/',
        'covid19-epiSummary-statements')

# CAN - COVID-19 Situational Awareness Dashboard (NML summary)
dl_file('https://health-infobase.canada.ca/src/data/covidLive/covid19-epiSummary-NML.csv',
        'can/nml-summary/',
        'covid19-epiSummary-NML')

# CAN - COVID-19 Situational Awareness Dashboard (NML weekly testing)
dl_file('https://health-infobase.canada.ca/src/data/covidLive/NML_weekly_testing.csv',
        'can/nml-weekly-testing/',
        'NML_weekly_testing')

# CAN - COVID-19 Situational Awareness Dashboard (Number of cases with detailed case report data)
dl_file('https://health-infobase.canada.ca/src/data/covidLive/covid19-nTotal.csv',
        'can/detailed-case-report-n/',
        'covid19-nTotal')

# CAN - COVID-19 Situational Awareness Dashboard (Cases and deaths by health region time series)
dl_file('https://health-infobase.canada.ca/src/data/covidLive/file_out_v5.csv',
        'can/cases-and-deaths-by-hr-time-series/',
        'file_out_v5')

# CAN - COVID-19 Situational Awareness Dashboard (Health region UID table)
dl_file('https://health-infobase.canada.ca/src/data/covidLive/covid19-healthregions-hruid.csv',
        'can/health-region-uid/',
        'covid19-healthregions-hruid')

# CAN - COVID-19 Situational Awareness Dashboard (Cases by exposure setting time series)
dl_file('https://health-infobase.canada.ca/src/data/covidLive/covid19-epiSummary-casesovertime.csv',
        'can/cases-by-exposure-time-series/',
        'covid19-epiSummary-casesovertime')

# CAN - COVID-19 Situational Awareness Dashboard (Epidemic curve by date of illness onset by age group)
dl_file('https://health-infobase.canada.ca/src/data/covidLive/covid19-epiSummary-epiCurveByAge.csv',
        'can/epidemic-curve-by-age/',
        'covid19-epiSummary-epiCurveByAge')

# CAN - COVID-19 Situational Awareness Dashboard (Severity by age group and sex)
dl_file('https://health-infobase.canada.ca/src/data/covidLive/covid19-epiSummary-severityUpdate.csv',
        'can/severity-by-age-and-sex/',
        'covid19-epiSummary-severityUpdate')

# CAN - COVID-19 Situational Awareness Dashboard (Cases by severity)
dl_file('https://health-infobase.canada.ca/src/data/covidLive/covid19-epiSummary-severity.csv',
        'can/cases-by-severity/',
        'covid19-epiSummary-severity')

# CAN - COVID-19 Situational Awareness Dashboard (Cases by age group and sex)
dl_file('https://health-infobase.canada.ca/src/data/covidLive/covid19-epiSummary-agegroups2.csv',
        'can/cases-by-age-and-sex/',
        'covid19-epiSummary-agegroups2')

# CAN - COVID-19 Situational Awareness Dashboard (Cases by probable exposure setting)
dl_file('https://health-infobase.canada.ca/src/data/covidLive/covid19-epiSummary-probableexposure2.csv',
        'can/cases-by-probable-exposure-setting/',
        'covid19-epiSummary-probableexposure2')

# CAN - COVID-19 Situational Awareness Dashboard (Symptoms summary)
dl_file('https://health-infobase.canada.ca/src/data/covidLive/covid19-epiSummary-symptoms.csv',
        'can/symptoms-summary/',
        'covid19-epiSummary-symptoms')

# CAN - COVID-19 Situational Awareness Dashboard (Situational awareness dashboard update time)
dl_file('https://health-infobase.canada.ca/src/data/covidLive/covid19-updateTime.csv',
        'can/situational-awareness-dashboard-update-time/',
        'covid19-updateTime')
# MB - Cases by status and RHA
dl_file('https://services.arcgis.com/mMUesHYPkXjaFGfS/arcgis/rest/services/mb_covid_cases_by_status_daily_rha/FeatureServer/0/query?f=json&where=1%3D1&returnGeometry=false&spatialRel=esriSpatialRelIntersects&outFields=*&groupByFieldsForStatistics=Date%2CRHA',
        'mb/cases-by-status-and-rha/',
        'cases-by-status-and-rha',
        mb_json_to_csv=True)

# MB - Manitoba Five-Day Test Positivity Rate
dl_file('https://services.arcgis.com/mMUesHYPkXjaFGfS/arcgis/rest/services/mb_covid_5_day_positivity_rate/FeatureServer/0/query?f=json&where=1%3D1&returnGeometry=false&spatialRel=esriSpatialRelIntersects&outFields=*&orderByFields=Date%20asc&resultOffset=0&resultRecordCount=32000&resultType=standard&cacheHint=true',
        'mb/five-day-test-positivity/',
        'five-day-test-positivity',
        mb_json_to_csv=True)

# NS - Coronavirus (COVID-19): case data
dl_file('https://novascotia.ca/coronavirus/data/ns-covid19-data.csv',
        'ns/case-data/',
        'ns-covid19-data')

# ON - Confirmed positive cases of COVID19 in Ontario
dl_file('https://data.ontario.ca/dataset/f4112442-bdc8-45d2-be3c-12efae72fb27/resource/455fd63b-603d-4608-8216-7d8647f43350/download/conposcovidloc.csv',
        'on/confirmed-positive-cases/',
        'conposcovidloc')

# ON - Status of COVID-19 cases in Ontario
dl_file('https://data.ontario.ca/dataset/f4f86e54-872d-43f8-8a86-3892fd3cb5e6/resource/ed270bb8-340b-41f9-a7c6-e8ef587e6d11/download/covidtesting.csv',
        'on/status-of-cases/',
        'covidtesting')

# ON - City of Toronto COVID-19 Summary
dl_file('https://docs.google.com/spreadsheets/d/1euhrML0rkV_hHF1thiA0G5vSSeZCqxHY/export?format=xlsx&id=1euhrML0rkV_hHF1thiA0G5vSSeZCqxHY',
        'on/toronto-covid-summary/',
        'CityofToronto_COVID-19_Data',
        ext='.xlsx')

# ON - COVID-19 Cases in Toronto
# run only on Wednesdays
if t.weekday() == 2:
        dl_file('https://ckan0.cf.opendata.inter.prod-toronto.ca/download_resource/e5bf35bc-e681-43da-b2ce-0242d00922ad?format=csv',
                'on/toronto-cases/',
                'COVID19_cases')

# ON - Ottawa cases and deaths
dl_file('https://www.arcgis.com/sharing/rest/content/items/cf9abb0165b34220be8f26790576a5e7/data',
        'on/ottawa-cases-and-deaths/',
        'COVID-19_Cases_and_Deaths_in_Ottawa_EN')

# ON - Ottawa outbreaks in healthcare institutions
dl_file('https://www.arcgis.com/sharing/rest/content/items/77078920fea8499dbb6f54cc69c03a90/data',
        'on/ottawa-outbreaks-in-healthcare-institutions/',
        'COVID-19_Outbreaks_in_Ottawa_Healthcare_Institutions_EN')

# ON - Ottawa hospitalization data
dl_file('https://www.arcgis.com/sharing/rest/content/items/02c99319ef44488e85cd4f96f5061f20/data',
        'on/ottawa-hospitalization/',
        'Hospitalizations_of_Ottawa_residents_with_confirmed_COVID-19')

# QC - COVID-19 data
dl_file('https://www.inspq.qc.ca/sites/default/files/covid/donnees/combine.csv',
        'qc/covid-data/',
        'combine',
        user=True)

# QC - COVID-19 data (charts)
dl_file('https://www.inspq.qc.ca/sites/default/files/covid/donnees/combine2.csv',
        'qc/covid-data-charts/',
        'combine2',
        user=True)

# QC - Deaths by RSS (health region) and living environment
dl_file('https://www.inspq.qc.ca/sites/default/files/covid/donnees/tableau-rpa.csv',
        'qc/deaths-by-rss-and-living-environment/',
        'tableau-rpa',
        user=True)

# QC - Cases by RSS (health region) and RLS (local service network)
dl_file('https://www.inspq.qc.ca/sites/default/files/covid/donnees/tableau-rls.csv',
        'qc/cases-by-rss-and-rls/',
        'tableau-rls',
        user=True)

# QC - List of schools with at least one reported case since September 1, 2020
dl_file('https://cdn-contenu.quebec.ca/cdn-contenu/sante/documents/Problemes_de_sante/covid-19/liste-ecole-cas-rapportes.pdf',
        'qc/list-of-schools-with-reported-cases/',
        'liste-ecole-cas-rapportes',
        ext = '.pdf')

# QC - Montréal cases and deaths by CIUSSS (integrated health and social services centres)
dl_file('https://santemontreal.qc.ca/fileadmin/fichiers/Campagnes/coronavirus/situation-montreal/ciusss.csv',
        'qc/montreal-cases-and-deaths-by-ciusss/',
        'ciusss',
        user=True)

# QC - Montréal cases by area
dl_file('https://santemontreal.qc.ca/fileadmin/fichiers/Campagnes/coronavirus/situation-montreal/municipal.csv',
        'qc/montreal-cases-by-area/',
        'municipal',
        user=True)

# QC - Montréal cases and deaths by age group
dl_file('https://santemontreal.qc.ca/fileadmin/fichiers/Campagnes/coronavirus/situation-montreal/grage.csv',
        'qc/montreal-cases-and-deaths-by-age-group/',
        'grage',
        user=True)

# QC - Montréal cases and deaths by sex
dl_file('https://santemontreal.qc.ca/fileadmin/fichiers/Campagnes/coronavirus/situation-montreal/sexe.csv',
        'qc/montreal-cases-and-deaths-by-sex/',
        'sexe',
        user=True)

# QC - Montréal epidemic curve
dl_file('https://santemontreal.qc.ca/fileadmin/fichiers/Campagnes/coronavirus/situation-montreal/courbe.csv',
        'qc/montreal-epidemic-curve/',
        'courbe',
        user=True)

# SK - Saskatchewan's Dashboard - Total Cases
dl_file('https://dashboard.saskatchewan.ca/export/cases/1557.csv',
        'sk/cases-by-region/',
        'cases')

# BC - Saskatchewan's Dashboard - Total Tests
dl_file('https://dashboard.saskatchewan.ca/export/tests/1556.csv',
        'sk/tests-by-region/',
        'tests')

# Other: QC - Covid Écoles Québec (Excel)
dl_file('https://drive.google.com/uc?export=download&id=1xOl0uhyx9IuHZfJuRH-OR7BcGFuWYUex',
        'other/qc/covid-ecoles-quebec-school-list/',
        'COVIDECOLESQUEBEC',
        ext = '.xlsx')

# Commit files
if mode == 'prod':
        print("Commiting files...")
        try:
                commit_files(file_list, commit_message)
                print(color('Commit successful!', Colors.green))
        except:
                print(background('Commit failed!', Colors.red))
