/**
 * LeadFlow ← Gmail. Sends new enquiries from your inbox to LeadFlow every 5 minutes.
 * 1. script.google.com → New project → paste this file. Set the 3 constants below.
 * 2. Run `setup` once and allow access. It creates a time trigger that runs `forwardNewEnquiries` every 5 minutes.
 * 3. Gmail filter (optional): put enquiries under the label in LABEL (e.g. mail sent to you via your website form).
 * Processed threads get the "leadflow-done" label so nothing is sent twice.
 */
const LEADFLOW_URL = "https://leadflow-ai-two-sooty.vercel.app/api/intake";
const INTAKE_KEY = "paste-your-INTAKE_KEY";          // same value as INTAKE_KEY in Vercel
const BUSINESS_ID = "ca";                            // a built-in demo id, or the id you saved in Settings
const LABEL = "";                                    // "" = whole inbox; or a label like "enquiries"

function setup() {
  ScriptApp.newTrigger("forwardNewEnquiries").timeBased().everyMinutes(5).create();
}

function forwardNewEnquiries() {
  const done = GmailApp.getUserLabelByName("leadflow-done") || GmailApp.createLabel("leadflow-done");
  const query = (LABEL ? `label:${LABEL} ` : "in:inbox ") + "is:unread newer_than:2d -label:leadflow-done";
  for (const thread of GmailApp.search(query, 0, 20)) {
    const msg = thread.getMessages().pop();
    const from = msg.getFrom();                      // "Name <email>"
    const m = from.match(/^(.*?)\s*<(.+)>$/);
    const body = msg.getPlainBody().slice(0, 3900);
    if (body.trim().length < 10) { thread.addLabel(done); continue; }
    const res = UrlFetchApp.fetch(LEADFLOW_URL, {
      method: "post", contentType: "application/json", muteHttpExceptions: true,
      headers: { "X-Intake-Key": INTAKE_KEY },
      payload: JSON.stringify({ business_id: BUSINESS_ID, enquiry: {
        channel: "email", from_name: m ? m[1].replace(/"/g, "") : "", from_email: m ? m[2] : from,
        subject: msg.getSubject().slice(0, 200), body: body } }),
    });
    if (res.getResponseCode() === 200) thread.addLabel(done);
    else console.log("LeadFlow error " + res.getResponseCode() + ": " + res.getContentText());
  }
}
