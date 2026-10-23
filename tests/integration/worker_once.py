"""Run an actual RQ worker with a fictional provider, only in the isolated stack."""
import os
from unittest.mock import Mock,patch
import frappe
from rq import SimpleWorker
from frappe.utils.background_jobs import get_queue

os.chdir('/testbench/sites')
frappe.init(site='whatsapp-test.localhost',sites_path='/testbench/sites');frappe.connect()
assert frappe.conf.db_host=='db'
queue=get_queue('default')
response=Mock(status_code=200,ok=True,json=Mock(return_value={'messages':[{'id':'wamid.rq-fixture'}]}))
with patch('requests.post',return_value=response),patch('requests.get',side_effect=AssertionError('External network forbidden')):
    worker=SimpleWorker([queue],connection=queue.connection)
    worker.work(burst=True,logging_level='ERROR')
