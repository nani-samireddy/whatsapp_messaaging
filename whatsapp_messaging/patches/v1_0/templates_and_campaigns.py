def execute():
    from whatsapp_messaging.messaging.template_editor import backfill
    from whatsapp_messaging.messaging.campaigns import backfill as split_campaigns
    backfill()
    split_campaigns()
