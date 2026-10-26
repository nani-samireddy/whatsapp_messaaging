"""Editable hospital starter content. No hospital facts or appointments are invented."""

def hospital(account_name):
    steps, choices = [], []
    def step(key, kind, prompt, next_step='', answer='', format='Text'):
        steps.append(dict(step_key=key, step_type=kind, prompt=prompt, next_step=next_step, answer_key=answer, answer_type=format))
    def option(source, key, label, target):
        choices.append(dict(from_step=source, choice_key=key, label=label, next_step=target))
    step('main_menu', 'Menu', 'Welcome to Riverbend Hospital. How can we help you today?')
    option('main_menu','appointment','Book an appointment','department')
    option('main_menu','information','Hospital information','information')
    option('main_menu','reception','Talk to reception','reception')
    step('department','Menu','Which department would you like to visit?',answer='department')
    for key,label in [('general_medicine','General medicine'),('orthopaedics','Orthopaedics'),('paediatrics','Paediatrics')]:
        option('department',key,label,'name')
    step('name','Question','What name should reception use for your appointment request?','preferred_date','name')
    step('preferred_date','Question','What date would you prefer? Enter YYYY-MM-DD. Reception will confirm availability.','review','preferred_date','Date')
    step('review','Menu','Please review your request:\nName: {{answers.name}}\nDepartment: {{answers.department}}\nPreferred date: {{answers.preferred_date}}\n\nWould you like to send this request to reception? This does not confirm an appointment.')
    option('review','submit','Send request','appointment_request')
    option('review','change','Change details','department')
    option('review','menu','Main menu','main_menu')
    step('appointment_request','Handoff','Thank you, {{answers.name}}. Reception has your appointment request for {{answers.preferred_date}} and will reply here to confirm availability. Your appointment is not confirmed yet.')
    step('information','Menu','What would you like to know about the hospital?')
    for key,label in [('hours','Opening hours'),('location','Location'),('departments','Departments')]:
        option('information',key,label,key)
    option('information','menu','Main menu','main_menu')
    step('hours','Message','[Add hospital opening hours here before publishing.]','information')
    step('location','Message','[Add the hospital address and directions here before publishing.]','information')
    step('departments','Message','[Add the hospital departments offered here before publishing.]','information')
    step('reception','Handoff','Reception will take over this conversation. Please wait for a team member to reply.')
    return dict(doctype='WhatsApp Conversation Flow',flow_title='Riverbend Hospital welcome',account=account_name,
        status='Draft',start_step='main_menu',trigger_mode='First message or keyword',keywords='hi, hello, menu',steps=steps,choices=choices)
