"""Bounded, deterministic conversation flows. No Frappe, templates or code execution."""
import copy
import json
import re
from datetime import date

KEY = re.compile(r'^[a-z][a-z0-9_]{0,39}$')
TOKEN = re.compile(r'{{\s*(contact_name|contact\.phone_number|answers\.[a-z][a-z0-9_]{0,39})\s*}}')
TYPES = {'Menu', 'Question', 'Message', 'Template', 'Handoff', 'End'}


def compile_definition(value, publishing=False, template_specs=None):
    steps = value.get('steps') or []
    choices = value.get('choices') or []
    if not 1 <= len(steps) <= 60 or len(choices) > 200:
        raise ValueError('Add between 1 and 60 steps, with at most 200 menu options.')
    result = {'start': value.get('start_step'), 'trigger_mode': value.get('trigger_mode') or 'First message or keyword',
              'keywords': [v.strip().casefold() for v in (value.get('keywords') or 'menu').split(',') if v.strip()], 'steps': {}}
    if result['trigger_mode'] not in ('First message or keyword', 'Keyword only') or len(result['keywords']) > 30:
        raise ValueError('Choose a valid start rule with at most 30 start words.')
    answer_keys = set()
    for row in steps:
        key = row.get('step_key') or ''
        if not KEY.fullmatch(key) or key in result['steps']:
            raise ValueError('Step names must be unique, start with a lowercase letter and contain only letters, numbers or underscores.')
        kind = row.get('step_type')
        prompt = '' if kind == 'Template' else str(row.get('prompt') or '').strip()
        if kind not in TYPES or (kind != 'Template' and (not prompt or len(prompt) > 1024)):
            raise ValueError('Each step needs an action and a message of at most 1,024 characters.')
        if publishing and '[Add ' in prompt:
            raise ValueError('Replace the sample hospital details before publishing.')
        remaining = TOKEN.sub('', prompt)
        if '{{' in remaining or '}}' in remaining:
            raise ValueError('Messages support only {{contact_name}}, {{contact.phone_number}} and {{answers.field_name}}.')
        item = {'kind': kind, 'prompt': prompt, 'next': row.get('next_step') or '', 'choices': []}
        if kind == 'Template':
            spec = (template_specs or {}).get(key)
            if not row.get('message_template') or not spec:
                raise ValueError('Choose a saved message template for ' + key + '.')
            try:
                raw = row.get('template_bindings') or '{}'
                if len(str(raw)) > 30000: raise ValueError()
                bindings = json.loads(raw) if isinstance(raw, str) else raw
                if spec.get('lookup'):bindings={}
                elif not isinstance(bindings, dict) or set(bindings) != set(spec['paths']): raise ValueError()
                if any(not isinstance(v, str) or not v.strip() or len(v)>1024 or '{{' in TOKEN.sub('',v) or '}}' in TOKEN.sub('',v) for v in bindings.values()): raise ValueError()
            except (ValueError,TypeError):
                raise ValueError('Fill in every template field using a collected answer, contact name or fixed text.')
            item.update(template=copy.deepcopy(spec), bindings=copy.deepcopy(bindings),lookup=copy.deepcopy(spec.get('lookup')))
        if kind == 'Question' or (kind == 'Menu' and row.get('answer_key')):
            answer = row.get('answer_key') or ''
            if not KEY.fullmatch(answer) or answer in answer_keys:
                raise ValueError('Each question needs a unique answer name, such as name or preferred_date.')
            answer_keys.add(answer)
            item.update(answer=answer, format=row.get('answer_type') or 'Text')
            if item['format'] not in ('Text', 'Date', 'Phone'):
                raise ValueError('Answer format must be Text, Date or Phone.')
            if kind == 'Question' and item['format'] == 'Phone':
                item['phone_mismatch'] = row.get('phone_mismatch_step') or ''
        result['steps'][key] = item
    if result['start'] not in result['steps']:
        raise ValueError('Choose an existing step as the first step.')
    for row in choices:
        source = result['steps'].get(row.get('from_step'))
        key, label, target = row.get('choice_key') or '', str(row.get('label') or '').strip(), row.get('next_step')
        if not source or source['kind'] != 'Menu' or not KEY.fullmatch(key) or not label or len(label) > 24 or target not in result['steps']:
            raise ValueError('Each menu option needs a menu step, unique option name, text of at most 24 characters and an existing destination step.')
        if any(c['key'] == key or c['label'].casefold() == label.casefold() for c in source['choices']):
            raise ValueError('Option names and labels must be unique within each menu.')
        source['choices'].append({'key': key, 'label': label, 'next': target})
    for key, step in result['steps'].items():
        if step['kind'] == 'Menu' and not 1 <= len(step['choices']) <= 10:
            raise ValueError('Each menu needs between 1 and 10 options.')
        if step['kind'] in ('Message', 'Template', 'Question') and step['next'] not in result['steps']:
            raise ValueError('Choose a valid next step for ' + key + '.')
        if step.get('lookup') and any(step['lookup'].get(k) not in result['steps'] for k in ('no_match','multiple_match')):raise ValueError('Choose the steps for no matching record and multiple matching records.')
        if step.get('format')=='Phone' and step['kind']=='Question' and step.get('phone_mismatch') not in result['steps']:
            raise ValueError('Choose a help step for a different registered phone number.')
        tokens = TOKEN.findall(step['prompt']) + [token for value in step.get('bindings', {}).values() for token in TOKEN.findall(value)]
        tokens += [token for c in (step.get('lookup') or {}).get('filters',[]) for token in TOKEN.findall(c['value'])]
        for token in tokens:
            if token.startswith('answers.') and token[8:] not in answer_keys:
                raise ValueError('Unknown answer in message: ' + token)
        # Message-only loops cannot wait for user input and are always invalid.
        seen, current = set(), key
        while current in result['steps'] and result['steps'][current]['kind'] in ('Message', 'Template'):
            if current in seen:
                raise ValueError('A message loop needs a menu, question or ending.')
            seen.add(current); current = result['steps'][current]['next']
        if current not in result['steps']:
            raise ValueError('Choose a valid next step for ' + key + '.')
    reachable, todo = set(), [result['start']]
    while todo:
        current = todo.pop()
        if current in reachable: continue
        reachable.add(current); step = result['steps'][current]
        todo.extend(c['next'] for c in step['choices'])
        if step['kind'] in ('Message', 'Template', 'Question'): todo.append(step['next'])
        if step.get('phone_mismatch'):todo.append(step['phone_mismatch'])
        if step.get('lookup'):todo.extend(step['lookup'][k] for k in ('no_match','multiple_match'))
    if set(result['steps']) - reachable:
        raise ValueError('Every step must be reachable from the first step.')
    visiting,done=set(),set()
    def check_auto(key):
        if key in done or result['steps'][key]['kind'] not in ('Message','Template'):return
        if key in visiting:raise ValueError('A message loop needs a menu, question or ending.')
        visiting.add(key);step=result['steps'][key];targets=[step['next']]
        if step.get('lookup'):targets += [step['lookup'][k] for k in ('no_match','multiple_match')]
        for target in targets:check_auto(target)
        visiting.remove(key);done.add(key)
    for key in result['steps']:check_auto(key)
    if publishing:
        incoming = {key: [] for key in result['steps']}
        for key, step in result['steps'].items():
            targets = [c['next'] for c in step['choices']]
            if step['kind'] in ('Message','Template','Question'): targets.append(step['next'])
            if step.get('phone_mismatch'):targets.append(step['phone_mismatch'])
            if step.get('lookup'):targets.extend(step['lookup'][k] for k in ('no_match','multiple_match'))
            for target in targets: incoming[target].append(key)
        guaranteed = {key: set(answer_keys) for key in result['steps']}
        guaranteed[result['start']] = set()
        for _ in range(120):
            changed = False
            for key in result['steps']:
                if key == result['start']: continue
                sources = [guaranteed[parent] | ({result['steps'][parent]['answer']} if result['steps'][parent].get('answer') else set()) for parent in incoming[key]]
                value = set.intersection(*sources) if sources else set()
                if value != guaranteed[key]: guaranteed[key]=value; changed=True
            if not changed: break
        for key, step in result['steps'].items():
            for value in [*step.get('bindings', {}).values(),*[c['value'] for c in (step.get('lookup') or {}).get('filters',[])]]:
                for token in TOKEN.findall(value):
                    if token.startswith('answers.') and token[8:] not in guaranteed[key]:
                        raise ValueError('Collect the answer ' + token[8:] + ' on every path before template step ' + key + '.')
    return result


def render(prompt, answers, contact_name='Contact', contact_phone=''):
    text = TOKEN.sub(lambda match: str(contact_name if match[1] == 'contact_name' else contact_phone if match[1]=='contact.phone_number' else answers.get(match[1][8:], ''))[:200], prompt)
    if len(text) > 4096: raise ValueError('The completed message is too long.')
    return text


def fresh_state(definition):
    return {'step': definition['start'], 'answers': {}, 'history': [], 'status': 'Active', 'invalid': 0}


def advance(definition, state=None, text='', choice=None, contact_name='Contact', today=None, contact_phone='', template_resolver=None):
    """Return outputs and next state. Choice IDs are validated by the service boundary."""
    state = copy.deepcopy(state or fresh_state(definition))
    if state['step'] not in definition['steps'] or len(state.get('answers', {})) > 60:
        raise ValueError('The conversation’s saved progress is invalid.')
    text = str(text or '').strip()
    outputs = []
    if text.casefold() in ('reception', 'human', 'staff'):
        state['status'] = 'Waiting for staff'
        return state, [{'kind': 'Handoff', 'text': 'Reception will take over this conversation. Please wait for a team member to reply.', 'choices': []}]
    if state['status'] != 'Active': return state, []
    if text.casefold() in set(definition['keywords']) | {'menu'}:
        state['step'] = definition['start']; state['history'] = []; text = ''; choice = None
    elif text.casefold() == 'back':
        state['step'] = state['history'].pop() if state['history'] else definition['start']; text = ''; choice = None
    elif text or choice:
        step = definition['steps'][state['step']]
        target = None
        if step['kind'] == 'Menu':
            for i, option in enumerate(step['choices'], 1):
                if choice == option['key'] or (choice is None and text.casefold() in (str(i), option['label'].casefold())):
                    if step.get('answer'): state['answers'][step['answer']] = option['label']
                    target = option['next']; break
        elif step['kind'] == 'Question' and choice is None:
            if step['format'] == 'Date':
                try:
                    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', text): raise ValueError()
                    parsed = date.fromisoformat(text)
                    if parsed < (today or date.today()): raise ValueError()
                    text = parsed.isoformat()
                except ValueError:
                    outputs.append({'kind': 'Message', 'text': 'Enter today or a future date as YYYY-MM-DD, for example ' + (today or date.today()).isoformat() + '.', 'choices': []})
                    text = ''
            elif step['format'] == 'Phone':
                number = re.sub(r'[\s().-]', '', text)
                if not re.fullmatch(r'\+?[1-9][0-9]{6,14}', number):
                    outputs.append({'kind':'Message','text':'Enter your registered mobile number with its country code, for example +91 followed by your mobile number.','choices':[]})
                    text = ''
                else: text = number.lstrip('+')
            elif len(text) > 200:
                outputs.append({'kind': 'Message', 'text': 'Please keep your answer to 200 characters or fewer.', 'choices': []}); text = ''
            if text:
                state['answers'][step['answer']] = text
                target = step['phone_mismatch'] if step['format']=='Phone' and text != re.sub(r'\D','',contact_phone) else step['next']
        if target:
            state['history'] = (state['history'] + [state['step']])[-60:]
            state['step'] = target; state['invalid'] = 0
        else:
            state['invalid'] = int(state.get('invalid', 0)) + 1
            if state['invalid'] >= 3:
                state['status'] = 'Waiting for staff'
                return state, [{'kind': 'Handoff', 'text': 'Let’s ask reception to help. A team member will take over this conversation.', 'choices': []}]
            if not outputs: outputs.append({'kind': 'Message', 'text': 'Please choose one of the options below, or type menu to start again or reception for help.', 'choices': []})
    for _ in range(60):
        step = definition['steps'][state['step']]
        output = {'kind': step['kind'], 'text': render(step['prompt'], state['answers'], contact_name, contact_phone), 'choices': step['choices'], 'step': state['step']}
        if step['kind'] == 'Template':
            for value in step['bindings'].values():
                for token in TOKEN.findall(value):
                    if token.startswith('answers.') and not state['answers'].get(token[8:]):
                        raise ValueError('Collect ' + token[8:] + ' before sending this template.')
            if step.get('lookup'):
                if not template_resolver:raise ValueError('A record lookup resolver is required.')
                found=template_resolver(step,state['answers'],contact_name,contact_phone)
                if found['outcome']!='matched':state['step']=step['lookup'][found['outcome']];continue
                values=found['values']
                output.update({k:found[k] for k in ('source_doctype','source_name') if k in found})
            else:values = [render(step['bindings'][path], state['answers'], contact_name, contact_phone) for path in step['template']['paths']]
            if not isinstance(values, list) or len(values)!=len(step['template']['paths']) or any(not isinstance(value,str) or not value.strip() or len(value)>1024 for value in values): raise ValueError('A template field is empty or too long.')
            body = re.sub(r'\{\{(\d+)\}\}', lambda m: values[int(m[1])-1], step['template']['body'])
            output['text'] = '\n\n'.join(value for value in [step['template']['header'],body,step['template']['footer']] if value)
            if len(output['text'])>4096: raise ValueError('The completed template is too long.')
            output['parameters'] = values
        outputs.append(output)
        if step['kind'] in ('Message', 'Template'): state['step'] = step['next']; continue
        if step['kind'] in ('Handoff', 'End'): state['status'] = 'Waiting for staff' if step['kind'] == 'Handoff' else 'Completed'
        return state, outputs
    raise ValueError('The flow contains too many consecutive message steps.')


def interactive(output, token):
    """Generate a Meta interactive object; IDs come from a conversation-bound token factory."""
    choices = output['choices']
    common = {'body': {'text': output['text']}, 'footer': {'text': 'Type menu to restart or reception for help.'}}
    if len(output['text']) > 1024: raise ValueError('A menu message cannot exceed 1,024 characters after inserting answers.')
    if len(choices) <= 3 and all(len(c['label']) <= 20 for c in choices):
        return dict(common, type='button', action={'buttons': [{'type': 'reply', 'reply': {'id': token(c['key']), 'title': c['label']}} for c in choices]})
    return dict(common, type='list', action={'button': 'View options', 'sections': [{'rows': [{'id': token(c['key']), 'title': c['label']} for c in choices]}]})
