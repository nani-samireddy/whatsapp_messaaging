import copy
import importlib.util
from pathlib import Path
import unittest
from datetime import date
ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'whatsapp_messaging/messaging'/f'{name}.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
e=load('flow_engine');starter=load('flow_starter')
class FlowEngineTests(unittest.TestCase):
    def setUp(self):self.draft=starter.hospital('fictional-sender');self.flow=e.compile_definition(self.draft)
    def start(self):return e.advance(self.flow)
    def choose(self,state,key):return e.advance(self.flow,state,choice=key,today=date(2026,10,24))
    def test_initial_three_options(self):
        state,messages=self.start();self.assertEqual([c['label'] for c in messages[0]['choices']],['Book an appointment','Hospital information','Talk to reception']);self.assertEqual(state['step'],'main_menu')
    def test_appointment_collects_department_name_date_and_hands_off(self):
        state,_=self.start();state,_=self.choose(state,'appointment');state,_=self.choose(state,'general_medicine')
        state,_=e.advance(self.flow,state,text='Training visitor');state,_=e.advance(self.flow,state,text='2026-10-27',today=date(2026,10,24))
        self.assertEqual(state['step'],'review');self.assertEqual(state['answers']['department'],'General medicine')
        state,messages=self.choose(state,'submit');self.assertEqual(state['status'],'Waiting for staff');self.assertIn('not confirmed',messages[-1]['text'])
    def test_numerical_and_label_text_choices(self):
        state,_=self.start();state,_=e.advance(self.flow,state,text='2');self.assertEqual(state['step'],'information')
        state,_=e.advance(self.flow,state,text='Location');self.assertEqual(state['step'],'information')
    def test_invalid_reply_three_times_hands_off(self):
        state,_=self.start()
        for _ in range(3):state,messages=e.advance(self.flow,state,text='Unrecognised option')
        self.assertEqual(state['status'],'Waiting for staff');self.assertEqual(messages[-1]['kind'],'Handoff')
    def test_invalid_date_does_not_advance(self):
        state,_=self.start();state,_=self.choose(state,'appointment');state,_=self.choose(state,'general_medicine');state,_=e.advance(self.flow,state,text='Visitor')
        for text in ('2026-10-23','not a date','20261027'):
            current,messages=e.advance(self.flow,state,text=text,today=date(2026,10,24));self.assertEqual(current['step'],'preferred_date');self.assertNotIn('preferred_date',current['answers'])
    def test_back_and_menu(self):
        state,_=self.start();state,_=self.choose(state,'appointment');state,_=e.advance(self.flow,state,text='back');self.assertEqual(state['step'],'main_menu')
        state,_=self.choose(state,'information');state,_=e.advance(self.flow,state,text='menu');self.assertEqual(state['step'],'main_menu')
    def test_manual_handoff_word(self):
        state,m=e.advance(self.flow,text='reception');self.assertEqual(state['status'],'Waiting for staff')
    def test_message_chain_returns_to_information_menu(self):
        state,_=self.start();state,_=self.choose(state,'information');state,m=self.choose(state,'hours');self.assertEqual([x['kind'] for x in m],['Message','Menu'])
    def test_starter_requires_real_hospital_details_before_publishing(self):
        with self.assertRaisesRegex(ValueError,'hospital details'):e.compile_definition(self.draft,publishing=True)
    def test_bad_destination_rejected(self):
        self.draft['choices'][0]['next_step']='unknown'
        with self.assertRaises(ValueError):e.compile_definition(self.draft)
    def test_unknown_interpolation_rejected(self):
        self.draft['steps'][0]['prompt']='{{frappe.db.sql("select 1")}}'
        with self.assertRaises(ValueError):e.compile_definition(self.draft)
    def test_answer_content_is_never_evaluated(self):
        self.assertEqual(e.render('{{answers.name}}',{'name':'{{frappe.secret}}'}),'{{frappe.secret}}')
    def test_message_loop_rejected(self):
        self.draft['steps'][0].update(step_type='Message',next_step='main_menu');self.draft['choices']=[c for c in self.draft['choices'] if c['from_step']!='main_menu']
        with self.assertRaisesRegex(ValueError,'loop'):e.compile_definition(self.draft)
    def test_unreachable_steps_rejected(self):
        self.draft['steps'].append(dict(step_key='lost',step_type='End',prompt='Goodbye'))
        with self.assertRaisesRegex(ValueError,'reachable'):e.compile_definition(self.draft)
    def test_button_and_list_payloads(self):
        state,m=self.start();obj=e.interactive(m[0],lambda key:'opaque-'+key);self.assertEqual(obj['type'],'button');self.assertEqual(len(obj['action']['buttons']),3)
        state,m=self.choose(state,'information');self.assertEqual(e.interactive(m[0],lambda key:key)['type'],'list')
    def test_preview_does_not_mutate_input(self):
        state,_=self.start();before=copy.deepcopy(state);self.choose(state,'appointment');self.assertEqual(state,before)
    def test_menu_variable_limit_after_rendering(self):
        message={'text':'a'*1025,'choices':[{'key':'x','label':'X'}]}
        with self.assertRaises(ValueError):e.interactive(message,lambda key:key)
    def test_completed_state_stays_finished(self):
        self.draft['steps'][0].update(step_type='End');self.draft['steps']=self.draft['steps'][:1];self.draft['choices']=[]
        flow=e.compile_definition(self.draft);state,_=e.advance(flow);_,messages=e.advance(flow,state,text='Hello');self.assertEqual(messages,[])
class FlowTemplateTests(unittest.TestCase):
    def setUp(self):
        self.draft = dict(start_step='ask', steps=[
            dict(step_key='ask',step_type='Question',prompt='Which date?',answer_key='date',answer_type='Date',next_step='confirmation'),
            dict(step_key='confirmation',step_type='Template',message_template='Confirmation',template_bindings='{"template_doctype.date":"{{answers.date}}"}',next_step='done'),
            dict(step_key='done',step_type='End',prompt='Thank you.')], choices=[])
        self.spec = dict(record='Confirmation',mode='Local message',body='Your appointment is on {{1}}.',paths=['template_doctype.date'],header='Appointment confirmed',footer='Training hospital')
    def compile(self,publishing=True):
        return e.compile_definition(self.draft,publishing=publishing,template_specs={'confirmation':self.spec})
    def test_template_uses_answer_and_framing_and_continues(self):
        flow=self.compile();state,_=e.advance(flow)
        state,messages=e.advance(flow,state,text='2026-10-27',today=date(2026,10,25))
        self.assertEqual(state['status'],'Completed');self.assertEqual(messages[0]['parameters'],['2026-10-27'])
        self.assertEqual(messages[0]['text'],'Appointment confirmed\n\nYour appointment is on 2026-10-27.\n\nTraining hospital')
    def test_requires_every_binding(self):
        self.draft['steps'][1]['template_bindings']='{}'
        with self.assertRaisesRegex(ValueError,'every template field'): self.compile()
    def test_cannot_publish_with_answer_collected_only_on_one_branch(self):
        self.draft['start_step']='menu'
        self.draft['steps'].insert(0,dict(step_key='menu',step_type='Menu',prompt='Choose'))
        self.draft['choices']=[dict(from_step='menu',choice_key='date',label='Give date',next_step='ask'),dict(from_step='menu',choice_key='skip',label='Skip',next_step='confirmation')]
        with self.assertRaisesRegex(ValueError,'every path'):self.compile()
        self.compile(publishing=False)
    def test_contact_phone_and_untrusted_answer_are_literal(self):
        self.draft['steps'][0].update(answer_type='Text')
        self.draft['steps'][1]['template_bindings']='{"template_doctype.date":"{{contact.phone_number}} / {{answers.date}}"}'
        flow=self.compile();state,_=e.advance(flow)
        _,messages=e.advance(flow,state,text='{{evil.secret}}',contact_phone='919000000001')
        self.assertEqual(messages[0]['parameters'],['919000000001 / {{evil.secret}}'])
    def test_missing_answer_does_not_send_template(self):
        flow=self.compile();state=e.fresh_state(flow);state['step']='confirmation'
        with self.assertRaisesRegex(ValueError,'Collect date'):e.advance(flow,state)
    def lookup(self):
        self.spec['lookup']=dict(doctype='ToDo',phone_field='wm_test_phone',filters=[dict(field='date',operator='=',value='{{answers.date}}')],no_match='none',multiple_match='many')
        self.draft['steps'].extend([dict(step_key='none',step_type='Handoff',prompt='Reception will help find your booking.'),dict(step_key='many',step_type='Handoff',prompt='Reception will check these bookings.')])
        self.draft['steps'][1]['template_bindings']='{}'
        return self.compile()
    def test_no_and_multiple_matches_do_not_output_confirmation(self):
        flow=self.lookup()
        for outcome,target in [('no_match','none'),('multiple_match','many')]:
            state,_=e.advance(flow)
            state,messages=e.advance(flow,state,text='2026-10-27',today=date(2026,10,25),template_resolver=lambda *args:dict(outcome=outcome))
            self.assertEqual(state['step'],target);self.assertEqual([m['kind'] for m in messages],['Handoff'])
    def test_matched_record_passes_source_and_values(self):
        flow=self.lookup();state,_=e.advance(flow)
        state,messages=e.advance(flow,state,text='2026-10-27',today=date(2026,10,25),template_resolver=lambda *args:dict(outcome='matched',values=['2026-10-27'],source_doctype='ToDo',source_name='TRAINING-1'))
        self.assertEqual(messages[0]['source_name'],'TRAINING-1');self.assertEqual(messages[0]['parameters'],['2026-10-27'])
    def test_invalid_lookup_parameter_count_is_rejected(self):
        flow=self.lookup();state,_=e.advance(flow)
        with self.assertRaises(ValueError):e.advance(flow,state,text='2026-10-27',today=date(2026,10,25),template_resolver=lambda *args:dict(outcome='matched',values=[]))
    def test_lookup_fallback_loop_is_rejected(self):
        self.lookup();self.spec['lookup']['no_match']='confirmation';self.draft['steps']=[s for s in self.draft['steps'] if s['step_key']!='none']
        with self.assertRaisesRegex(ValueError,'loop'):self.compile()
    def test_lookup_answer_must_be_collected_on_every_path(self):
        self.lookup();self.draft['start_step']='confirmation';self.draft['steps']=self.draft['steps'][1:]
        self.draft['steps'].append(dict(step_key='ask',step_type='Question',prompt='Date?',answer_key='date',next_step='confirmation'))
        self.draft['steps'][2]['next_step']='ask';self.draft['steps'][2]['step_type']='Message'
        with self.assertRaisesRegex(ValueError,'every path'):self.compile()

class RegisteredPhoneTests(unittest.TestCase):
    def setUp(self):
        self.draft=dict(start_step='confirm_phone',steps=[
            dict(step_key='confirm_phone',step_type='Menu',prompt='Is +{{contact.phone_number}} your registered number?'),
            dict(step_key='registered_phone',step_type='Question',prompt='Enter your registered number with country code.',answer_key='registered_phone',answer_type='Phone',phone_mismatch_step='verify',next_step='found'),
            dict(step_key='found',step_type='End',prompt='Your latest booking details follow.'),
            dict(step_key='verify',step_type='Handoff',prompt='Reception will verify +{{answers.registered_phone}}.')],choices=[
            dict(from_step='confirm_phone',choice_key='yes',label='Yes, this number',next_step='found'),
            dict(from_step='confirm_phone',choice_key='no',label='No, enter number',next_step='registered_phone')])
        self.flow=e.compile_definition(self.draft,publishing=True)
    def enter_number(self,text):
        state,_=e.advance(self.flow,contact_phone='919000000001')
        state,messages=e.advance(self.flow,state,choice='no',contact_phone='919000000001')
        self.assertEqual(state['step'],'registered_phone');self.assertEqual(messages[0]['kind'],'Question')
        return e.advance(self.flow,state,text=text,contact_phone='919000000001')
    def test_confirmation_shows_current_number(self):
        _,messages=e.advance(self.flow,contact_phone='919000000001')
        self.assertIn('+919000000001',messages[0]['text'])
    def test_no_asks_for_registered_number_and_matching_number_continues(self):
        for text in ['+91 90000 00001','919000000001','+91 (90000)-00001']:
            state,_=self.enter_number(text);self.assertEqual(state['status'],'Completed');self.assertEqual(state['answers']['registered_phone'],'919000000001')
    def test_different_number_is_saved_for_reception(self):
        state,messages=self.enter_number('+91 90000 00002')
        self.assertEqual(state['status'],'Waiting for staff');self.assertEqual(state['answers']['registered_phone'],'919000000002');self.assertNotIn('booking details',messages[0]['text'])
    def test_invalid_phone_stays_at_question(self):
        for text in ['abc','123','+91+9000000001','0000000000']:
            state,_=self.enter_number(text);self.assertEqual(state['step'],'registered_phone');self.assertNotIn('registered_phone',state['answers'])
    def test_phone_question_requires_a_verification_destination(self):
        self.draft['steps'][1]['phone_mismatch_step']='missing'
        with self.assertRaisesRegex(ValueError,'help step'):e.compile_definition(self.draft)

if __name__=='__main__':unittest.main()
