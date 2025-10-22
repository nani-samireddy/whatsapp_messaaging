import mimetypes
import os
import frappe
import requests
from frappe.integrations.utils import make_post_request
from frappe.utils.file_manager import get_file
from requests_toolbelt import MultipartEncoder
from whatsapp_messaging.utils import mime_type_to_message_type
from whatsapp_messaging.utils.config import get_cloud_api_url, get_headers

# Setup logger
# # frappe.utils.logger.set_log_level("DEBUG")
logger = frappe.logger("whatsapp_messaging", allow_site=True, file_count=50)


@frappe.whitelist()
def upload_media_to_whatsapp(media_file, docname):
	'''This function is used to upload media to WhatsApp'''
	doc = frappe.get_doc("WhatsApp Media", docname)
	frappe.log_error(f"Uploading media for doc: {docname}")
	doc.status = "Starting upload..."
	doc.save()

	# Get file
	file_data = get_file(media_file)
	
 	# Get the headers and URL
	headers = get_headers( phone_number_id=doc.phone_number_id, content_type="multipart/form-data" )
	url = get_cloud_api_url(phone_number_id=doc.phone_number_id, type="media")
	mime_type = mimetypes.guess_type(media_file)[0]

	# Set the media content type
	doc.content_type = mime_type
	doc.status = "Uploading to media API..."
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
			doc.status = "Upload completed successfully"
		else:
			doc.status = "Upload failed - no media ID received"
		doc.save()

	except Exception as e:
		logger.error(f"Error in upload_media_to_whatsapp: {str(e)}", exc_info=True)
		doc.status = "Upload failed"
		doc.save()


@frappe.whitelist()
def upload_media_with_resumable_upload(media_file, docname):
	'''This function uploads media using Facebook's resumable upload API and then also uploads to traditional media API'''
	doc = frappe.get_doc("WhatsApp Media", docname)
	frappe.log_error(f"Starting resumable upload for doc: {docname}")
	
	try:
		# Get file data and details
		file_data = get_file(media_file)
		file_content = file_data[1]
		file_name = file_data[0]
		file_length = len(file_content)
		mime_type = mimetypes.guess_type(media_file)[0]
		
		# Set the media content type and initial status
		doc.content_type = mime_type
		doc.status = "Starting resumable upload..."
		doc.save()
		
		# Step 1: Start upload session
		upload_session_id = start_upload_session(doc.phone_number_id, file_name, file_length, mime_type)
		
		if not upload_session_id:
			raise Exception("Failed to start upload session")
		
		doc.status = "Upload session started, uploading file..."
		doc.save()
			
		# Step 2: Upload the file to resumable API
		file_handle = upload_file_to_session(doc.phone_number_id, upload_session_id, file_content, mime_type)
		
		if not file_handle:
			raise Exception("Failed to complete resumable upload")
		
		# Save the file handle
		doc.file_handle = file_handle
		doc.status = "Resumable upload completed, uploading to media API..."
		doc.save()
		
		# Step 3: Also upload to traditional media API
		media_id = upload_to_traditional_media_api(doc, file_data, mime_type)
		
		if media_id:
			doc.media_id = media_id
			doc.status = "Both uploads completed successfully"
		else:
			doc.status = "Resumable upload completed, traditional upload failed"
			
		doc.save()
		
	except Exception as e:
		logger.error(f"Error in upload_media_with_resumable_upload: {str(e)}", exc_info=True)
		doc.status = "Upload failed"
		doc.save()


def upload_to_traditional_media_api(doc, file_data, mime_type):
	'''Upload to traditional WhatsApp media API and return media_id'''
	try:
		# Get the headers and URL
		headers = get_headers(phone_number_id=doc.phone_number_id, content_type="multipart/form-data")
		url = get_cloud_api_url(phone_number_id=doc.phone_number_id, type="media")
		
		payload = {
			"file": (file_data[0], file_data[1], mime_type),
			"messaging_product": "whatsapp",
			"type": mime_type
		}
		payload = MultipartEncoder(payload)
		headers["Content-Type"] = payload.content_type
		response = make_post_request(url, data=payload, headers=headers)

		# If media id is present, return it
		if response.get('id'):
			logger.info(f"Traditional media upload successful, media_id: {response.get('id')}")
			return response.get('id')
		else:
			logger.error(f"Traditional media upload failed: {response}")
			return None

	except Exception as e:
		logger.error(f"Error in upload_to_traditional_media_api: {str(e)}", exc_info=True)
		return None


def start_upload_session(phone_number_id, file_name, file_length, file_type):
	'''Start a resumable upload session with Facebook Graph API'''
	try:
		# Get phone number ID document to retrieve app ID
		phone_number_doc = frappe.get_doc("WhatsApp Phone Number ID", phone_number_id)
		
		# Get WhatsApp settings to get app ID
		settings = frappe.get_doc("WhatsApp Settings")
		
		app_id = settings.app_id
		if not app_id:
			frappe.throw("App ID not configured. Please configure App ID in WhatsApp Settings")
			
		# Construct the upload session URL
		url = f"{settings.whatsapp_api_url}/{settings.whatsapp_api_version}/{app_id}/uploads"
		
		params = {
			'file_name': file_name,
			'file_length': file_length,
			'file_type': file_type
		}
		
		headers = {
			'Authorization': f'Bearer {phone_number_doc.access_token}'
		}
		
		response = requests.post(url, params=params, headers=headers)
		response_data = response.json()
		
		if response.status_code == 200 and 'id' in response_data:
			upload_session_id = response_data['id']
			logger.info(f"Started upload session: {upload_session_id}")
			return upload_session_id
		else:
			logger.error(f"Failed to start upload session: {response_data}")
			return None
			
	except Exception as e:
		logger.error(f"Error starting upload session: {str(e)}", exc_info=True)
		return None


def upload_file_to_session(phone_number_id, upload_session_id, file_content, mime_type):
	'''Upload file content to the upload session'''
	try:
		phone_number_doc = frappe.get_doc("WhatsApp Phone Number ID", phone_number_id)
		settings = frappe.get_doc("WhatsApp Settings")
		
		# Construct the upload URL
		url = f"{settings.whatsapp_api_url}/{settings.whatsapp_api_version}/{upload_session_id}"
		
		headers = {
			'Authorization': f'Bearer {phone_number_doc.access_token}',
			'Content-Type': mime_type,
			'file_offset': '0'
		}
		
		response = requests.post(url, headers=headers, data=file_content)
		response_data = response.json()
		
		if response.status_code == 200 and 'h' in response_data:
			file_handle = response_data['h']
			logger.info(f"File uploaded successfully. Handle: {file_handle}")
			return file_handle
		else:
			logger.error(f"Failed to upload file: {response_data}")
			return None
			
	except Exception as e:
		logger.error(f"Error uploading file to session: {str(e)}", exc_info=True)
		return None


def resume_interrupted_upload(phone_number_id, upload_session_id):
	'''Check the status of an interrupted upload and get the file offset'''
	try:
		phone_number_doc = frappe.get_doc("WhatsApp Phone Number ID", phone_number_id)
		settings = frappe.get_doc("WhatsApp Settings")
		
		# Construct the status check URL
		url = f"{settings.whatsapp_api_url}/{settings.whatsapp_api_version}/{upload_session_id}"
		
		headers = {
			'Authorization': f'Bearer {phone_number_doc.access_token}'
		}
		
		response = requests.get(url, headers=headers)
		response_data = response.json()
		
		if response.status_code == 200 and 'file_offset' in response_data:
			file_offset = response_data['file_offset']
			logger.info(f"Upload session status - file_offset: {file_offset}")
			return file_offset
		else:
			logger.error(f"Failed to get upload status: {response_data}")
			return None
			
	except Exception as e:
		logger.error(f"Error checking upload status: {str(e)}", exc_info=True)
		return None


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
			logger.info("processing uploaded media")
			# If the media type is Upload, get the media_id or file_handle, content_type.
			document_type = mime_type_to_message_type(doc.content_type)
			
			# Use file_handle if available (from resumable upload), otherwise use media_id
			if doc.file_handle:
				media_data[document_type] = {
					"h": doc.file_handle,
					"caption": doc.caption
				}
			elif doc.media_id:
				media_data[document_type] = {
					"id": doc.media_id,
					"caption": doc.caption
				}
			else:
				# If neither is available, this might be an error case
				logger.error(f"No file_handle or media_id available for document {doc.name}")
				media_data[document_type] = {
					"caption": doc.caption
				}

		return [document_type, media_data]

	except Exception as e:
		logger.error(f"Error in process_whatsapp_media: {str(e)}", exc_info=True)
		return ["text", media_data]
