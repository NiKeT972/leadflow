/**
 * LeadFlow → Google Sheets webhook.
 * 1. Create a Google Sheet, then Extensions → Apps Script, and paste this file.
 * 2. Deploy → New deployment → type "Web app" → Execute as: Me → Who has access: Anyone → Deploy.
 * 3. Copy the web app URL into GOOGLE_SHEETS_WEBHOOK_URL (Vercel → Settings → Environment Variables), then redeploy.
 * Each approved lead is appended as one row; the header row is created on the first call.
 */
const COLUMNS = ["received_at", "business", "channel", "name", "email", "phone", "category", "services",
                 "budget_inr", "timeline", "score", "priority", "status"];

function doPost(e) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Leads")
             || SpreadsheetApp.getActiveSpreadsheet().insertSheet("Leads");
  if (sheet.getLastRow() === 0) sheet.appendRow(COLUMNS);
  const row = JSON.parse(e.postData.contents);
  sheet.appendRow(COLUMNS.map(c => row[c] ?? ""));
  return ContentService.createTextOutput(JSON.stringify({ ok: true })).setMimeType(ContentService.MimeType.JSON);
}
