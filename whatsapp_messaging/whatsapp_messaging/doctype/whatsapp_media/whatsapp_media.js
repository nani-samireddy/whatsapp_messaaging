// // Copyright (c) 2024, nani-samireddy and contributors
// // For license information, please see license.txt
let isSaving = false;
frappe.ui.form.on("WhatsApp Media", {
	after_save: async function (frm) {
		if (!isSaving) {
			fetchFileFromFrappe(frm.doc.wa_media_attachment, frm);
		}
	},

});

async function fetchFileFromFrappe(fileName, frm) {
	try {
		await frappe.call({
			method: "whatsapp_messaging.utils.wa_get_file_upload_info",
			args: {
				file_name: fileName
			},
			callback: async function (response) {
				console.log(response.message);
				if (!response.message) {
					console.error("File not found");
					return;
				}



				const fileBlob = new Blob([response.message['file']], { type: response.message['content_type'] });
				const file = new File([fileBlob], fileName, { type: fileBlob.type });
				console.log(file);
				// Upload the file to WhatsApp
				 await uploadToWhatsApp(
					{
						file: file,
						token: response.message['token'],
						frm: frm
					}
				);
			}
		});

	} catch (error) {
		console.error("Error fetching file:", error);
	}
}

async function uploadToWhatsApp({file, token, frm}) {
	try {
		if (!file) {
			console.error("File not found");
			return;
		}

		// Create FormData and append the file and other necessary data
		const formdata = new FormData();
		formdata.append("messaging_product", "whatsapp");
		formdata.append("file", file);



		// Set up the request options for WhatsApp API
		const requestOptions = {
			method: "POST",
			body: formdata,
			headers: {
				"Authorization": `Bearer ${token}`,
			},
		};
		// Send the request to WhatsApp
		const response = await fetch(`https://graph.facebook.com/v20.0/358748870656654/media`, requestOptions);

		const result = await response.json();
		console.log(result);
		isSaving = true;
		// Set the media_id in the form
		frm.set_value("wa_media_id", result.id);
		frm.save();
		frm.reload_doc();
	} catch (error) {
		console.error("Error uploading file to WhatsApp:", error);
	}
}
