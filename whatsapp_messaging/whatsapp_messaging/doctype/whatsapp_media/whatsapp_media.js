// // Copyright (c) 2024, nani-samireddy and contributors
// // For license information, please see license.txt

frappe.ui.form.on("WhatsApp Media", {
	after_save: async function (frm) {
		fetchFileFromFrappe(frm.doc.wa_media_attachment);
	},

});

async function fetchFileFromFrappe(fileName) {
	try {
		await frappe.call({
			method: "whatsapp_messaging.utils.wa_get_file",
			args: {
				file_name: fileName
			},
			callback: async function (response) {
				console.log(response.message);
				// Convert the response into a Blob to send it to WhatsApp
				const fileBlob = new Blob([response.message], { type: "image/jpeg" });
				const file = new File([fileBlob], fileName, { type: fileBlob.type });
				console.log(file);
				// Upload the file to WhatsApp
				await uploadToWhatsApp(file);
			}
		});

	} catch (error) {
		console.error("Error fetching file:", error);
	}
}

async function uploadToWhatsApp(file) {
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
				"Authorization": "Bearer EAAGZBlWy1nCsBO64cnK1BtrJllyNA1Jjpxg1aJkNUVMgFaqk72B5vFG2Yk8nKHrxHubJAa19Cc9vK6SVUswRTuCKZBvPE6fMnNuf1g4ZAs9asJUBLkGBioAFozOZCTA8NFCzZCQkU3Cjxt3Dp8SrcQByjkoKxRFnSIv8uoOwhdqZAtAQazJrqGc8cKDSLazqZC8VxH5NhrmPkbolEft55DtysAZCGrsZD"
			},
		};

		console.log("Uploading file to WhatsApp...");
		for ([key, value] of formdata.entries()) {
			console.log(key, value);
		}
		// Send the request to WhatsApp
		const response = await fetch(`https://graph.facebook.com/v20.0/358748870656654/media`, requestOptions);

		const result = await response.text();
		console.log(result);

	} catch (error) {
		console.error("Error uploading file to WhatsApp:", error);
	}
}
