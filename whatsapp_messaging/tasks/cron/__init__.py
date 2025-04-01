# This file handles the scheduling of messages to be sent via WhatsApp.

from whatsapp_messaging.controller import wm_handle_scheduled_messages
from whatsapp_messaging.utils import decode_from_alphanumeric

'''
@NOTE: This is a hack to dynamically create functions that we can pass to the scheduler.
- We pass the scheduled_message_handler_{encoded_template_name} as the method to the Scheduled Job Type.
- And the following __getattr__ function is called when the function is requested.
- Then It takes the function name decodes it and creates a function reference to the wm_handle_scheduled_messages function with the decoded template name.
- In this way we are getting the template name dynamically and also creating a function reference dynamically.
- This is a hack and should not be used for any other purpose. Do not use this module for any other purpose.
'''
def __getattr__(name):
    '''
    This function checks if the function name starts with scheduled_message_handler_ and then decodes the template name and creates a function reference to the wm_handle_scheduled_messages function.
    '''
    if name.startswith("scheduled_message_handler_"):
        template_name = name.replace("scheduled_message_handler_", "")

        def scheduled_function():
            return wm_handle_scheduled_messages(decode_from_alphanumeric(template_name))

        return scheduled_function  # Return the function reference

    raise AttributeError(f"Module '{__name__}' has no attribute '{name}'")
