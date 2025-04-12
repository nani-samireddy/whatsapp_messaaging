import mimetypes
import frappe
from frappe.integrations.utils import make_post_request
from frappe.utils.file_manager import get_file
from requests_toolbelt import MultipartEncoder
from whatsapp_messaging.utils import mime_type_to_message_type
from whatsapp_messaging.utils.config import get_cloud_api_url, get_headers


def upload_media_to_whatsapp(media_file, doc):
	'''This function is used to upload media to WhatsApp'''
	doc.media_id = "Upload media..."
	doc.save()

	# Get file
	file_data = get_file(media_file)

 	# Get the headers and URL
	headers = get_headers( "multipart/form-data" )
	url = get_cloud_api_url("media")
	mime_type = mimetypes.guess_type(media_file)[0]

	# Set the media content type
	doc.content_type = mime_type
	doc.save()
	try:
		payload = {
			"file" : (file_data[0], file_data[1], mime_type),
			"messaging_product": "whatsapp",
			"type": mime_type
		}
		payload = MultipartEncoder(payload)
		headers["Content-Type"] = payload.content_type
		response = make_post_request(url, data=payload, headers=headers)

		# If media id is present, save it to the doc
		if response.get('id'):
			doc.media_id = response.get('id')
		else:
			doc.media_id = "Failed to upload media"
		doc.save()

	except Exception as e:
		frappe.log_error(f"Error in upload_media_to_whatsapp: {str(e)}")
		doc.media_id = "Failed to upload media"
		doc.save()

def process_whatsapp_media(doc):
	'''This function is used to process the WhatsApp media
	#### Args:
		doc (doc): The WhatsApp Media document

  	Returns:
		list: A list containing the document type and media data
 	'''
	media_data = {}
	try:
		# Check if media type is URL or Upload
		if doc.media_type == "URL":
			# If the media type is URL, set the type and link
			document_type = doc.document_type
			media_data[document_type] = {
				"link": doc.media_url,
				"caption": doc.caption
			}
		elif doc.media_type == "Upload":
			# If the media type is Upload, get the media_id, content_type.
			document_type = mime_type_to_message_type(doc.content_type)
			media_data[document_type] = {
				"id": doc.media_id,
				"caption": doc.caption
			}

		return [document_type, media_data]

	except Exception as e:
		frappe.log_error(f"Error in process_whatsapp_media: {str(e)}")
		return ["text", media_data]
