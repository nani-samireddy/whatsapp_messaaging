"""
Data migration script to convert language codes to language names.
This script updates existing WhatsApp Message Template records to use the new
user-friendly language names instead of language codes.
"""

import frappe

def execute():
	"""
	Migrate existing language codes to language names in WhatsApp Message Template
	"""
	# Mapping from old language codes to new language names
	code_to_name_mapping = {
		"af": "Afrikaans",
		"sq": "Albanian", 
		"ar": "Arabic",
		"ar_EG": "Arabic (Egypt)",
		"ar_AE": "Arabic (UAE)",
		"ar_LB": "Arabic (Lebanon)",
		"ar_MA": "Arabic (Morocco)",
		"ar_QA": "Arabic (Qatar)",
		"az": "Azerbaijani",
		"be_BY": "Belarusian",
		"bn": "Bengali",
		"bn_IN": "Bengali (India)",
		"bg": "Bulgarian",
		"ca": "Catalan",
		"zh_CN": "Chinese (China)",
		"zh_HK": "Chinese (Hong Kong)",
		"zh_TW": "Chinese (Taiwan)",
		"hr": "Croatian",
		"cs": "Czech",
		"da": "Danish",
		"prs_AF": "Dari",
		"nl": "Dutch",
		"nl_BE": "Dutch (Belgium)",
		"en": "English",
		"en_GB": "English (UK)",
		"en_US": "English (US)",
		"en_AE": "English (UAE)",
		"en_AU": "English (Australia)",
		"en_CA": "English (Canada)",
		"en_GHA": "English (Ghana)",
		"en_IE": "English (Ireland)",
		"en_IN": "English (India)",
		"en_JM": "English (Jamaica)",
		"en_MY": "English (Malaysia)",
		"en_NZ": "English (New Zealand)",
		"en_QA": "English (Qatar)",
		"en_SG": "English (Singapore)",
		"en_UG": "English (Uganda)",
		"en_ZA": "English (South Africa)",
		"et": "Estonian",
		"fil": "Filipino",
		"fi": "Finnish",
		"fr": "French",
		"fr_BE": "French (Belgium)",
		"fr_CA": "French (Canada)",
		"fr_CH": "French (Switzerland)",
		"fr_CI": "French (Ivory Coast)",
		"fr_MA": "French (Morocco)",
		"ka": "Georgian",
		"de": "German",
		"de_AT": "German (Austria)",
		"de_CH": "German (Switzerland)",
		"el": "Greek",
		"gu": "Gujarati",
		"ha": "Hausa",
		"he": "Hebrew",
		"hi": "Hindi",
		"hu": "Hungarian",
		"id": "Indonesian",
		"ga": "Irish",
		"it": "Italian",
		"ja": "Japanese",
		"kn": "Kannada",
		"kk": "Kazakh",
		"rw_RW": "Kinyarwanda",
		"ko": "Korean",
		"ky_KG": "Kyrgyz (Kyrgyzstan)",
		"lo": "Lao",
		"lv": "Latvian",
		"lt": "Lithuanian",
		"mk": "Macedonian",
		"ms": "Malay",
		"ml": "Malayalam",
		"mr": "Marathi",
		"nb": "Norwegian",
		"ps_AF": "Pashto",
		"fa": "Persian",
		"pl": "Polish",
		"pt_BR": "Portuguese (Brazil)",
		"pt_PT": "Portuguese (Portugal)",
		"pa": "Punjabi",
		"ro": "Romanian",
		"ru": "Russian",
		"sr": "Serbian",
		"si_LK": "Sinhala",
		"sk": "Slovak",
		"sl": "Slovenian",
		"es": "Spanish",
		"es_AR": "Spanish (Argentina)",
		"es_CL": "Spanish (Chile)",
		"es_CO": "Spanish (Colombia)",
		"es_CR": "Spanish (Costa Rica)",
		"es_DO": "Spanish (Dominican Republic)",
		"es_EC": "Spanish (Ecuador)",
		"es_HN": "Spanish (Honduras)",
		"es_MX": "Spanish (Mexico)",
		"es_PA": "Spanish (Panama)",
		"es_PE": "Spanish (Peru)",
		"es_ES": "Spanish (Spain)",
		"es_UY": "Spanish (Uruguay)",
		"sw": "Swahili",
		"sv": "Swedish",
		"ta": "Tamil",
		"te": "Telugu",
		"th": "Thai",
		"tr": "Turkish",
		"uk": "Ukrainian",
		"ur": "Urdu",
		"uz": "Uzbek",
		"vi": "Vietnamese",
		"zu": "Zulu"
	}
	
	# Get all templates with language codes that need migration
	templates = frappe.get_all(
		"WhatsApp Message Template", 
		fields=["name", "whatsapp_template_language"],
		filters={"whatsapp_template_language": ["is", "set"]}
	)
	
	updated_count = 0
	
	for template in templates:
		current_language = template.get("whatsapp_template_language")
		if current_language and current_language in code_to_name_mapping:
			# Update to language name
			new_language_name = code_to_name_mapping[current_language]
			frappe.db.set_value(
				"WhatsApp Message Template", 
				template["name"], 
				"whatsapp_template_language", 
				new_language_name
			)
			updated_count += 1
			print(f"Updated {template['name']}: {current_language} -> {new_language_name}")
	
	frappe.db.commit()
	print(f"Migration completed. Updated {updated_count} template(s).")

if __name__ == "__main__":
	execute()